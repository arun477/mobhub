import re
import logging
from ..agent import BaseAgent, AgentPersonality, AgentStatus
from ..events import Event, EventType

logger = logging.getLogger("engine.agents.org_profiler")


class OrgProfilerAgent(BaseAgent):

    def __init__(self, hub_id: str, target_name: str = "", target_uuid: str = "", **kwargs):
        super().__init__(
            hub_id=hub_id,
            agent_type="org_profiler",
            name=f"OrgProfiler({target_name})",
            personality=AgentPersonality(
                approach="comprehensive and structured",
                expertise=["company research", "organizational analysis"],
                style="structured org data with key facts",
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
                await self._profile_org()

    async def _profile_org(self):
        self.log_action("profile", f"Deep profiling org: {self.target_name}")

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
        all_urls = []

        searches = [
            f"{self.target_name} about company",
            f"{self.target_name} founders CEO team",
            f"{self.target_name} official site twitter github",
        ]

        for query in searches:
            try:
                results = await web_search(query=query, limit=5)
                for r in results:
                    if r.get("content"):
                        search_context += f"\n{r.get('title', '')}: {r['content'][:400]}"
                    if r.get("url"):
                        all_urls.append({"url": r["url"], "title": r.get("title", "")})
                self.log_action("search", f"'{query[:40]}' — {len(results)} results")
            except Exception:
                pass

        if not search_context:
            self.status = AgentStatus.COMPLETED
            return

        try:
            profile_response = await llm(messages=[
                {"role": "system", "content": f"""Extract a structured profile for this organization. Return EXACTLY this format (leave empty if unknown, do NOT guess):

TYPE: <company, research lab, nonprofit, etc.>
FOUNDED: <year>
HQ: <city, country>
CEO: <name>
KEY_PEOPLE: <comma-separated names>
PRODUCTS: <comma-separated main products/services>
BIO: <2-3 sentence description>
WEBSITE: <official website URL if found, or empty>
TWITTER: <official Twitter/X URL if found, or empty>
GITHUB: <official GitHub URL if found, or empty>

IMPORTANT: Only include URLs you are confident belong to THIS organization "{self.target_name}". Do NOT guess."""},
                {"role": "user", "content": f"Organization: {self.target_name}\n\nSearch results:\n{search_context[:3000]}\n\nURLs found:\n" + "\n".join(f"- {u['url']} ({u['title']})" for u in all_urls[:15])},
            ], max_tokens=500)

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
                    "type": "org_type",
                    "founded": "founded",
                    "hq": "headquarters",
                    "ceo": "ceo",
                    "key_people": "key_people",
                    "products": "products",
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
                    "website": ("Website", r"https?://\S+\.\S+"),
                    "twitter": ("Twitter/X", r"https?://(twitter\.com|x\.com)/\w+"),
                    "github": ("GitHub", r"https?://github\.com/[\w-]+"),
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
                if fields.get("type"):
                    parts.append(f"{fields['type']}.")
                if fields.get("founded") and fields.get("hq"):
                    parts.append(f"Founded {fields['founded']}, based in {fields['hq']}.")
                parts.append(bio)
                await update_node(hub_id=self.hub_id, uuid=self.target_uuid, summary=" ".join(parts)[:500])
            if add_episode:
                episode_parts = [f"Organization profile: {self.target_name}"]
                for k, v in fields.items():
                    if k not in ("website", "twitter", "github"):
                        episode_parts.append(f"- {k.title()}: {v}")
                await add_episode(
                    hub_id=self.hub_id,
                    name=f"Org: {self.target_name}",
                    content="\n".join(episode_parts),
                    source_desc="OrgProfiler deep research",
                )

            self.log_action("complete", f"Org profile complete: {self.target_name}")

        except Exception as e:
            self.log_action("profile", f"Failed: {e}", status="failed")

        await self._find_logo(save_asset)

        self.status = AgentStatus.COMPLETED
        await self.emit(EventType.AGENT_COMPLETED, {
            "agent_type": "org_profiler",
            "target_name": self.target_name,
        })

    async def _find_logo(self, save_asset):
        """Try clearbit logo API (free, reliable)."""
        if not save_asset or not self.target_uuid:
            return
        # Clean org name for domain guess
        clean = self.target_name.lower().replace(" ", "").replace("-", "")
        logo_url = f"https://logo.clearbit.com/{clean}.com"
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.head(logo_url, follow_redirects=True)
                if resp.status_code == 200:
                    await save_asset(hub_id=self.hub_id, node_uuid=self.target_uuid,
                                     asset_type="image", name=f"Logo", content=logo_url, mime_type="image/png")
                    self.log_action("asset", f"Found logo for {self.target_name}")
        except Exception:
            pass
