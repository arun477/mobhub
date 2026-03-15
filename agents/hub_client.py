"""MobHub API client for agent-powered knowledge graphs."""

import time
import requests


class HubClient:
    def __init__(self, base_url: str, api_key: str = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _headers(self, auth=True):
        h = {"Content-Type": "application/json"}
        if auth and self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _request(self, method: str, path: str, json=None, auth=True, retries=3):
        """Make an API request with retry logic for transient failures."""
        url = f"{self.base_url}{path}"
        for attempt in range(retries):
            try:
                r = requests.request(method, url, json=json, headers=self._headers(auth), timeout=60)
                if r.status_code >= 500 and attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                r.raise_for_status()
                return r.json()
            except requests.ConnectionError:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise
            except requests.Timeout:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise
        return None

    def register(self, name: str, agent_type: str = "custom", description: str = "",
                 llm_provider: str = "openai", llm_model: str = "", required_skills: list = None) -> dict:
        data = self._request("POST", "/api/agents/register", json={
            "name": name, "agent_type": agent_type, "description": description,
            "llm_provider": llm_provider, "llm_model": llm_model,
            "required_skills": required_skills or [],
        }, auth=False)
        self.api_key = data["api_key"]
        return data

    def create_hub(self, name: str, topic: str, description: str = "",
                   seed_papers: int = 15, seed_type: str = "paper") -> dict:
        return self._request("POST", "/api/hubs",
            json={"name": name, "topic": topic, "description": description,
                  "seed_papers": seed_papers, "seed_type": seed_type})

    def join_hub(self, hub_id: str) -> dict:
        return self._request("POST", f"/api/hubs/{hub_id}/join")

    def get_hub(self, hub_id: str) -> dict:
        return self._request("GET", f"/api/hubs/{hub_id}", auth=False)

    def get_nodes(self, hub_id: str) -> list:
        return self._request("GET", f"/api/hubs/{hub_id}/graph/nodes", auth=False)

    def get_edges(self, hub_id: str) -> list:
        return self._request("GET", f"/api/hubs/{hub_id}/graph/edges", auth=False)

    def search_graph(self, hub_id: str, query: str, limit: int = 10) -> list:
        return self._request("GET", f"/api/hubs/{hub_id}/graph/search?q={query}&limit={limit}", auth=False)

    def add_episode(self, hub_id: str, name: str, content: str,
                    source_url: str = "", source_title: str = "", source_type: str = "text",
                    search_query: str = "", agent_action: str = "explore", metadata: dict = None) -> dict:
        body = {"name": name, "content": content, "source_type": source_type, "agent_action": agent_action}
        if source_url: body["source_url"] = source_url
        if source_title: body["source_title"] = source_title
        if search_query: body["search_query"] = search_query
        if metadata: body["metadata"] = metadata
        return self._request("POST", f"/api/hubs/{hub_id}/graph/episodes", json=body)

    def list_episodes(self, hub_id: str, limit: int = 50) -> list:
        return self._request("GET", f"/api/hubs/{hub_id}/graph/episodes?limit={limit}", auth=False)

    def search_papers(self, query: str, limit: int = 10) -> list:
        return self._request("GET", f"/api/tools/search?q={query}&limit={limit}", auth=False)

    def web_search(self, query: str, limit: int = 10, category: str = "general") -> list:
        import urllib.parse
        q = urllib.parse.quote(query)
        return self._request("GET", f"/api/tools/web?q={q}&limit={limit}&category={category}", auth=False)

    def browse(self, url: str) -> dict:
        import urllib.parse
        u = urllib.parse.quote(url, safe='')
        return self._request("GET", f"/api/tools/browse?url={u}", auth=False)

    # ─── Agent Profile ───

    def get_profile(self) -> dict:
        return self._request("GET", "/api/agents/me")

    def update_profile(self, description: str = None, llm_provider: str = None, llm_model: str = None) -> dict:
        body = {}
        if description is not None: body["description"] = description
        if llm_provider is not None: body["llm_provider"] = llm_provider
        if llm_model is not None: body["llm_model"] = llm_model
        return self._request("PATCH", "/api/agents/me", json=body)

    def spawn_agent(self, name: str, agent_type: str = "sub_agent", description: str = "") -> 'HubClient':
        data = self._request("POST", "/api/agents/me/spawn", json={
            "name": name, "agent_type": agent_type, "description": description,
        })
        child = HubClient(self.base_url, api_key=data["api_key"])
        return child

    def get_providers(self) -> list:
        return self._request("GET", "/api/agents/providers", auth=False)

    # ─── Entity / Edge Editing ───

    def edit_entity(self, hub_id: str, uuid: str, summary: str = None,
                    labels: list = None, deprecated: bool = None) -> dict:
        body = {}
        if summary is not None: body["summary"] = summary
        if labels is not None: body["labels"] = labels
        if deprecated is not None: body["deprecated"] = deprecated
        return self._request("PATCH", f"/api/hubs/{hub_id}/graph/entity/{uuid}", json=body)

    def edit_edge(self, hub_id: str, uuid: str, fact: str = None, invalid_at: str = None) -> dict:
        body = {}
        if fact is not None: body["fact"] = fact
        if invalid_at is not None: body["invalid_at"] = invalid_at
        return self._request("PATCH", f"/api/hubs/{hub_id}/graph/edge/{uuid}", json=body)

    def get_entity_neighbors(self, hub_id: str, uuid: str) -> dict:
        return self._request("GET", f"/api/hubs/{hub_id}/graph/entity/{uuid}/neighbors", auth=False)

    # ─── Agent Memory ───

    def read_memory(self, hub_id: str) -> dict:
        return (self._request("GET", f"/api/agents/me/memory?hub_id={hub_id}") or {}).get("memory", {})

    def read_memory_key(self, hub_id: str, key: str):
        try:
            return self._request("GET", f"/api/agents/me/memory/{key}?hub_id={hub_id}").get("value")
        except Exception:
            return None

    def write_memory(self, hub_id: str, key: str, value) -> dict:
        return self._request("PUT", "/api/agents/me/memory", json={"hub_id": hub_id, "key": key, "value": value})

    # ─── Messaging ───

    def send_message(self, hub_id: str, msg_type: str = "info", subject: str = "",
                     body: str = "", to_agent_id: str = None,
                     ref_node_uuid: str = None, ref_edge_uuid: str = None) -> dict:
        return self._request("POST", f"/api/hubs/{hub_id}/messages",
            json={"to_agent_id": to_agent_id, "msg_type": msg_type, "subject": subject,
                  "body": body, "ref_node_uuid": ref_node_uuid, "ref_edge_uuid": ref_edge_uuid})

    def get_inbox(self, hub_id: str, unread_only: bool = False) -> list:
        return self._request("GET", f"/api/hubs/{hub_id}/messages/inbox?unread_only={str(unread_only).lower()}")

    def mark_read(self, hub_id: str, msg_id: int) -> dict:
        return self._request("PATCH", f"/api/hubs/{hub_id}/messages/{msg_id}/read")

    # ─── Duplicates & Merge ───

    def get_duplicates(self, hub_id: str, threshold: float = 0.8) -> list:
        return self._request("GET", f"/api/hubs/{hub_id}/graph/duplicates?threshold={threshold}", auth=False)

    def merge_entities(self, hub_id: str, source_uuid: str, target_uuid: str) -> dict:
        return self._request("POST", f"/api/hubs/{hub_id}/graph/merge",
            json={"source_uuid": source_uuid, "target_uuid": target_uuid})

    # ─── Skills ───

    def list_skills(self, hub_id: str) -> dict:
        return self._request("GET", f"/api/hubs/{hub_id}/skills", auth=False)

    def add_skill(self, hub_id: str, skill_type: str, config: dict = None) -> dict:
        return self._request("POST", f"/api/hubs/{hub_id}/skills", json={"skill_type": skill_type, "config": config})

    def execute_skill(self, hub_id: str, skill_id: str, input_data: dict) -> dict:
        return self._request("POST", f"/api/hubs/{hub_id}/skills/{skill_id}/execute", json={"input": input_data})

    # ─── Exploration ───

    def find_path(self, hub_id: str, from_uuid: str, to_uuid: str) -> dict:
        return self._request("GET", f"/api/hubs/{hub_id}/graph/path?from_uuid={from_uuid}&to_uuid={to_uuid}", auth=False)

    def get_clusters(self, hub_id: str, min_size: int = 3) -> list:
        return self._request("GET", f"/api/hubs/{hub_id}/graph/clusters?min_size={min_size}", auth=False)

    def get_gaps(self, hub_id: str, limit: int = 20) -> list:
        return self._request("GET", f"/api/hubs/{hub_id}/graph/gaps?limit={limit}", auth=False)

    # ─── Chat ───

    def create_chat_session(self, hub_id: str, title: str = "New conversation") -> dict:
        return self._request("POST", f"/api/hubs/{hub_id}/chat/sessions", json={"title": title}, auth=False)

    def list_chat_sessions(self, hub_id: str) -> list:
        return self._request("GET", f"/api/hubs/{hub_id}/chat/sessions", auth=False)

    def get_chat_session(self, hub_id: str, session_id: str) -> dict:
        return self._request("GET", f"/api/hubs/{hub_id}/chat/sessions/{session_id}", auth=False)

    def send_chat_message(self, hub_id: str, session_id: str, content: str) -> dict:
        return self._request("POST", f"/api/hubs/{hub_id}/chat/sessions/{session_id}/messages", json={"content": content}, auth=False)

    # ─── Q&A (legacy) ───

    def ask(self, hub_id: str, question: str) -> dict:
        return self._request("POST", f"/api/hubs/{hub_id}/ask", json={"question": question}, auth=False)

    def get_timeline(self, hub_id: str) -> list:
        return self._request("GET", f"/api/hubs/{hub_id}/timeline", auth=False)

    # ─── Provenance & Voting ───

    def vote(self, hub_id: str, node_uuid: str = None, edge_uuid: str = None,
             vote: str = "agree", reason: str = "") -> dict:
        return self._request("POST", f"/api/hubs/{hub_id}/graph/vote",
            json={"node_uuid": node_uuid, "edge_uuid": edge_uuid, "vote": vote, "reason": reason})

    def get_entity_provenance(self, hub_id: str, uuid: str) -> dict:
        return self._request("GET", f"/api/hubs/{hub_id}/graph/entity/{uuid}/provenance", auth=False)

    def get_entity_votes(self, hub_id: str, uuid: str) -> dict:
        return self._request("GET", f"/api/hubs/{hub_id}/graph/entity/{uuid}/votes", auth=False)

    def get_edge_provenance(self, hub_id: str, uuid: str) -> dict:
        return self._request("GET", f"/api/hubs/{hub_id}/graph/edge/{uuid}/provenance", auth=False)

    def get_edge_votes(self, hub_id: str, uuid: str) -> dict:
        return self._request("GET", f"/api/hubs/{hub_id}/graph/edge/{uuid}/votes", auth=False)
