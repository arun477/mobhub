from . import graph, llm


SYSTEM_PROMPT = """You are a knowledge assistant for MobHub, a collaborative knowledge graph platform. Answer questions using the provided knowledge graph data.

Rules:
- Answer based on the entities and facts provided in the graph context.
- Be specific — reference entity names and facts from the graph.
- If information isn't in the graph context, say "this isn't in the current knowledge graph" — don't make things up.
- Keep answers concise but thorough.
- If facts are marked [SUPERSEDED], note the information may be outdated.
- You can have back-and-forth conversations, remembering what was discussed earlier.
- When listing entities, include their type labels (e.g., [Person], [Organization])."""


async def _build_graph_context(hub_id: str, query: str, conversation_topic: str = "") -> tuple[str, dict]:
    """
    Build graph context by:
    1. Getting ALL entities (so nothing is missed)
    2. Searching for relevant edges/facts
    3. If conversation has a topic, also search with that context
    """
    all_nodes = []
    try:
        all_nodes = await graph.get_all_nodes(hub_id)
    except Exception:
        pass

    search_results = []
    try:
        search_results = await graph.search_graph(hub_id, query, limit=20)
    except Exception:
        pass

    if conversation_topic and conversation_topic.lower() != query.lower():
        try:
            topic_results = await graph.search_graph(hub_id, conversation_topic, limit=10)
            # Merge, avoiding duplicates
            existing_facts = {r["fact"] for r in search_results}
            for r in topic_results:
                if r["fact"] not in existing_facts:
                    search_results.append(r)
        except Exception:
            pass

    lines = []

    if all_nodes:
        lines.append(f"ALL ENTITIES IN THIS KNOWLEDGE GRAPH ({len(all_nodes)}):")
        for n in all_nodes[:100]:
            labels = [l for l in (n.get("labels") or []) if l != "Entity"]
            label_str = f" [{', '.join(labels)}]" if labels else ""
            summary = (n.get("summary") or "")[:150]
            lines.append(f"  - {n['name']}{label_str}: {summary}")

    if search_results:
        lines.append(f"\nRELEVANT FACTS/RELATIONSHIPS ({len(search_results)}):")
        for r in search_results:
            valid = " [SUPERSEDED]" if r.get("invalid_at") else ""
            lines.append(f"  - {r['fact']}{valid}")

    context = "\n".join(lines) if lines else "No knowledge found in the graph."

    query_words = set(query.lower().split())
    relevant_nodes = []
    for n in all_nodes:
        name_words = set(n["name"].lower().split())
        summary_words = set((n.get("summary") or "").lower().split())
        # Check if entity name or summary overlaps with query
        if name_words & query_words or len(name_words & summary_words & query_words) > 0:
            relevant_nodes.append(n)

    if not relevant_nodes:
        relevant_nodes = sorted(all_nodes, key=lambda n: len(n.get("summary", "") or ""), reverse=True)[:10]

    citations = {
        "entities": [{"uuid": n["uuid"], "name": n["name"]} for n in relevant_nodes[:15]],
        "facts": [{"fact": r["fact"]} for r in search_results[:10]],
    }
    return context, citations


async def ask(hub_id: str, question: str, provider: str = "openai", model: str = "") -> dict:
    """Single-turn Q&A."""
    context, citations = await _build_graph_context(hub_id, question)

    try:
        answer = await llm.chat(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Knowledge Graph Context:\n{context}\n\nQuestion: {question}"},
            ],
            provider=provider, model=model, max_tokens=600,
        )
    except Exception as e:
        answer = f"LLM error: {e}"

    return {
        "question": question, "answer": answer, "citations": citations,
        "context_entities": len(citations.get("entities", [])),
        "context_facts": len(citations.get("facts", [])),
    }


async def chat(hub_id: str, history: list[dict], new_message: str,
               provider: str = "openai", model: str = "") -> dict:
    """Multi-turn chat grounded in knowledge graph."""

    conversation_topic = ""
    if history:
        first_user = next((m["content"] for m in history if m["role"] == "user"), "")
        conversation_topic = first_user[:100]

    context, citations = await _build_graph_context(hub_id, new_message, conversation_topic)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"Knowledge graph context (ALL entities and relevant facts):\n{context}"},
    ]
    for msg in history[-20:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": new_message})

    try:
        answer = await llm.chat(messages=messages, provider=provider, model=model, max_tokens=800)
    except Exception as e:
        answer = f"LLM error: {e}"

    title_suggestion = None
    if len(history) == 0:
        try:
            title_suggestion = await llm.chat(
                messages=[
                    {"role": "system", "content": "Generate a very short title (3-6 words). Return only the title."},
                    {"role": "user", "content": new_message},
                    {"role": "assistant", "content": answer[:200]},
                ],
                provider=provider, model=model, max_tokens=30,
            )
            title_suggestion = title_suggestion.strip().strip('"')
        except Exception:
            pass

    return {"answer": answer, "citations": citations, "title_suggestion": title_suggestion}
