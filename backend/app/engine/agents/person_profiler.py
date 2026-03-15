import re
import logging
from ..agent import BaseAgent, AgentPersonality, AgentStatus
from ..events import Event, EventType

logger = logging.getLogger("engine.agents.person_profiler")


class PersonProfilerAgent(BaseAgent):

    def __init__(self, hub_id: str, target_name: str = "", target_uuid: str = "", **kwargs):
        super().__init__(
            hub_id=hub_id,
            agent_type="person_profiler",
            name=f"PersonProfiler({target_name})",
            personality=AgentPersonality(
                approach="focused and thorough",
                expertise=["people research", "social profiles", "professional history"],
                style="structured profile data",
            ),
            **kwargs,
        )
        self.target_name = target_name
        self.target_uuid = target_uuid

    def get_triggers(self) -> list[EventType]:
        return [EventType.AGENT_SPAWNED]

    async def handle_event(self, event: Event):
        if event.type == EventType.AGENT_SPAWNED:
            if event.data.get("child_agent_id") == self.id:
                await self._profile_person()

    async def _profile_person(self):
        self.log_action("profile", f"Deep profiling: {self.target_name}")

        web_search = self.tools.get("web_search")
        llm = self.tools.get("llm_chat")
        update_node = self.tools.get("graph_update_node")
        add_episode = self.tools.get("graph_add_episode")
        save_meta = self.tools.get("save_entity_meta")
        save_asset = self.tools.get("save_entity_asset")

        if not web_search or not llm:
            self.status = AgentStatus.COMPLETED
            return

        search_context = ""
        all_urls = []  # collect URLs for later LLM validation

        searches = [
            f"{self.target_name}",
            f"{self.target_name} role title organization",
            f"{self.target_name} twitter OR linkedin OR github site:twitter.com OR site:linkedin.com OR site:github.com",
        ]

        for query in searches:
            try:
                results = await web_search(query=query, limit=5)
                for r in results:
                    if r.get("content"):
                        search_context += f"\n{r.get('title', '')}: {r['content'][:400]}"
                    url = r.get("url", "")
                    title = r.get("title", "")
                    if url:
                        all_urls.append({"url": url, "title": title})
                self.log_action("search", f"'{query[:40]}' — {len(results)} results")
            except Exception as e:
                logger.debug(f"Search failed: {e}")

        if not search_context:
            self.status = AgentStatus.COMPLETED
            return

        try:
            profile_response = await llm(messages=[
                {"role": "system", "content": f"""Extract a structured profile for this person. Return EXACTLY this format (leave empty if unknown, do NOT guess):

ROLE: <current title/role>
ORGANIZATION: <current company/org>
LOCATION: <city, country>
EXPERTISE: <comma-separated areas>
BIO: <2-3 sentence biography>
TWITTER: <exact Twitter/X URL if found in the search results, or empty>
LINKEDIN: <exact LinkedIn URL if found in the search results, or empty>
GITHUB: <exact GitHub URL if found in the search results, or empty>
WEBSITE: <personal website URL if found, or empty>

IMPORTANT: Only include social URLs that you are confident belong to THIS specific person "{self.target_name}". Do NOT guess URLs. Leave empty if unsure."""},
                {"role": "user", "content": f"Person: {self.target_name}\n\nSearch results:\n{search_context[:3000]}\n\nURLs found:\n" + "\n".join(f"- {u['url']} ({u['title']})" for u in all_urls[:15])},
            ], max_tokens=500)

            # Parse fields
            fields = {}
            for line in profile_response.strip().split("\n"):
                if ":" in line:
                    key, _, value = line.partition(":")
                    key = key.strip().lower()
                    value = value.strip()
                    if value and value not in ("unknown", "N/A", "n/a", "", "empty", "not found"):
                        fields[key] = value
            if save_meta and self.target_uuid:
                meta_mappings = {
                    "role": "role",
                    "organization": "organization",
                    "location": "location",
                    "expertise": "expertise",
                }
                stored = 0
                for src_key, meta_key in meta_mappings.items():
                    if src_key in fields:
                        await save_meta(hub_id=self.hub_id, node_uuid=self.target_uuid,
                                        key=meta_key, value=fields[src_key])
                        stored += 1
                if stored:
                    self.log_action("metadata", f"Stored {stored} fields for {self.target_name}")
            if save_asset and self.target_uuid:
                social_links = {
                    "twitter": ("Twitter/X", r"https?://(twitter\.com|x\.com)/\w+"),
                    "linkedin": ("LinkedIn", r"https?://(www\.)?linkedin\.com/in/[\w-]+"),
                    "github": ("GitHub", r"https?://github\.com/[\w-]+"),
                    "website": ("Website", r"https?://\S+"),
                }
                for key, (label, pattern) in social_links.items():
                    url = fields.get(key, "")
                    if url and re.match(pattern, url):
                        await save_asset(hub_id=self.hub_id, node_uuid=self.target_uuid,
                                         asset_type="url", name=label, content=url)
                        self.log_action("asset", f"Verified {label}: {url[:50]}")
            bio = fields.get("bio", "")
            if bio and update_node and self.target_uuid:
                parts = []
                if fields.get("role") and fields.get("organization"):
                    parts.append(f"{fields['role']} at {fields['organization']}.")
                parts.append(bio)
                await update_node(hub_id=self.hub_id, uuid=self.target_uuid, summary=" ".join(parts)[:500])
                self.log_action("enrich", f"Updated profile for {self.target_name}")
            if add_episode:
                episode_parts = [f"Profile of {self.target_name}:"]
                for k, v in fields.items():
                    if k not in ("twitter", "linkedin", "github", "website"):
                        episode_parts.append(f"- {k.title()}: {v}")
                await add_episode(
                    hub_id=self.hub_id,
                    name=f"Profile: {self.target_name}",
                    content="\n".join(episode_parts),
                    source_desc="PersonProfiler deep research",
                )

            self.log_action("complete", f"Profile complete for {self.target_name}")

        except Exception as e:
            self.log_action("profile", f"Failed: {e}", status="failed")

        self.status = AgentStatus.COMPLETED
        await self.emit(EventType.AGENT_COMPLETED, {
            "agent_type": "person_profiler",
            "target_name": self.target_name,
        })
