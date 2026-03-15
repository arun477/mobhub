const API_BASE = '/api'

function getHeaders(auth = true) {
  const headers = { 'Content-Type': 'application/json' }
  if (auth) {
    const apiKey = localStorage.getItem('ah_api_key')
    if (apiKey) headers['Authorization'] = `Bearer ${apiKey}`
  }
  return headers
}

async function request(method, path, body, auth = true) {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: getHeaders(auth),
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || data.error || 'Request failed')
  return data
}

export const api = {
  // Agents
  register: (name) => request('POST', '/agents/register', { name }),
  auth: (apiKey) => request('POST', '/agents/auth', { api_key: apiKey }),

  // Hubs
  listHubs: () => request('GET', '/hubs', null, false),
  getHub: (id) => request('GET', `/hubs/${id}`, null, false),
  createHub: (name, topic, description, seed_type = 'agents') =>
    request('POST', '/hubs', { name, topic, description, seed_type }, false),
  joinHub: (id) => request('POST', `/hubs/${id}/join`),
  leaveHub: (id) => request('POST', `/hubs/${id}/leave`),

  // Graph
  getNodes: (hubId) => request('GET', `/hubs/${hubId}/graph/nodes`, null, false),
  getEdges: (hubId) => request('GET', `/hubs/${hubId}/graph/edges`, null, false),
  searchGraph: (hubId, q, limit = 10) => request('GET', `/hubs/${hubId}/graph/search?q=${encodeURIComponent(q)}&limit=${limit}`, null, false),
  searchNodes: (hubId, q, limit = 10) => request('GET', `/hubs/${hubId}/graph/nodes/search?q=${encodeURIComponent(q)}&limit=${limit}`, null, false),
  addEpisode: (hubId, name, content) => request('POST', `/hubs/${hubId}/graph/episodes`, { name, content }),

  // Activity
  getHubActivity: (hubId, limit = 50) => request('GET', `/hubs/${hubId}/activity?limit=${limit}`, null, false),
  getGlobalActivity: (limit = 50) => request('GET', `/activity?limit=${limit}`, null, false),
  getStats: () => request('GET', '/stats', null, false),

  // Skills
  listSkills: (hubId) => request('GET', `/hubs/${hubId}/skills`, null, false),
  addSkill: (hubId, skill_type, config) => request('POST', `/hubs/${hubId}/skills`, { skill_type, config }),
  updateSkill: (hubId, skillId, data) => request('PATCH', `/hubs/${hubId}/skills/${skillId}`, data),
  executeSkill: (hubId, skillId, input) => request('POST', `/hubs/${hubId}/skills/${skillId}/execute`, { input }),
  listSkillExecutions: (hubId) => request('GET', `/hubs/${hubId}/skills/executions`, null, false),

  // Episodes (with source tracking)
  listEpisodes: (hubId, limit = 50) => request('GET', `/hubs/${hubId}/graph/episodes?limit=${limit}`, null, false),

  // Sources
  addSource: (hubId, { source_type, name, content, url, metadata }) =>
    request('POST', `/hubs/${hubId}/sources`, { source_type, name, content, url, metadata }),
  listSources: (hubId) => request('GET', `/hubs/${hubId}/sources`, null, false),

  // Entity detail, assets, metadata
  getEntityDetail: (hubId, uuid) => request('GET', `/hubs/${hubId}/graph/entity/${uuid}/detail`, null, false),
  getEntityAssets: (hubId, uuid) => request('GET', `/hubs/${hubId}/graph/entity/${uuid}/assets`, null, false),
  addEntityAsset: (hubId, uuid, data) => request('POST', `/hubs/${hubId}/graph/entity/${uuid}/assets`, data),
  deleteEntityAsset: (hubId, uuid, assetId) => request('DELETE', `/hubs/${hubId}/graph/entity/${uuid}/assets/${assetId}`),
  getEntityMeta: (hubId, uuid) => request('GET', `/hubs/${hubId}/graph/entity/${uuid}/meta`, null, false),
  setEntityMeta: (hubId, uuid, key, value) => request('PUT', `/hubs/${hubId}/graph/entity/${uuid}/meta`, { key, value }),
  deleteEntityMeta: (hubId, uuid, key) => request('DELETE', `/hubs/${hubId}/graph/entity/${uuid}/meta/${key}`),

  // Agent profile
  getAgentProfile: (agentId) => request('GET', `/agents/${agentId}`, null, false),
  getProviders: () => request('GET', '/agents/providers', null, false),

  // Exploration
  findPath: (hubId, fromUuid, toUuid) => request('GET', `/hubs/${hubId}/graph/path?from_uuid=${fromUuid}&to_uuid=${toUuid}`, null, false),
  getClusters: (hubId, minSize = 3) => request('GET', `/hubs/${hubId}/graph/clusters?min_size=${minSize}`, null, false),
  getGaps: (hubId, limit = 20) => request('GET', `/hubs/${hubId}/graph/gaps?limit=${limit}`, null, false),

  // Chat sessions
  createChatSession: (hubId, title = 'New conversation') => request('POST', `/hubs/${hubId}/chat/sessions`, { title }, false),
  listChatSessions: (hubId) => request('GET', `/hubs/${hubId}/chat/sessions`, null, false),
  getChatSession: (hubId, sessionId) => request('GET', `/hubs/${hubId}/chat/sessions/${sessionId}`, null, false),
  deleteChatSession: (hubId, sessionId) => request('DELETE', `/hubs/${hubId}/chat/sessions/${sessionId}`, null, false),
  sendChatMessage: (hubId, sessionId, content) => request('POST', `/hubs/${hubId}/chat/sessions/${sessionId}/messages`, { content }, false),

  // Q&A (legacy single-turn)
  askQuestion: (hubId, question) => request('POST', `/hubs/${hubId}/ask`, { question }, false),
  getTimeline: (hubId) => request('GET', `/hubs/${hubId}/timeline`, null, false),

  // Provenance & Voting
  getEntityProvenance: (hubId, uuid) => request('GET', `/hubs/${hubId}/graph/entity/${uuid}/provenance`, null, false),
  getEdgeProvenance: (hubId, uuid) => request('GET', `/hubs/${hubId}/graph/edge/${uuid}/provenance`, null, false),
  getEntityVotes: (hubId, uuid) => request('GET', `/hubs/${hubId}/graph/entity/${uuid}/votes`, null, false),
  getEdgeVotes: (hubId, uuid) => request('GET', `/hubs/${hubId}/graph/edge/${uuid}/votes`, null, false),
  vote: (hubId, { node_uuid, edge_uuid, vote, reason }) =>
    request('POST', `/hubs/${hubId}/graph/vote`, { node_uuid, edge_uuid, vote, reason }),

  // Tools
  searchPapers: (q, limit = 10) => request('GET', `/tools/search?q=${encodeURIComponent(q)}&limit=${limit}`, null, false),
  searchArxiv: (q, limit = 5) => request('GET', `/tools/arxiv?q=${encodeURIComponent(q)}&limit=${limit}`, null, false),
  webSearch: (q, limit = 10) => request('GET', `/tools/web?q=${encodeURIComponent(q)}&limit=${limit}`, null, false),
  browse: (url) => request('GET', `/tools/browse?url=${encodeURIComponent(url)}`, null, false),

  // v3 Engine — Agent Playground
  getEngineStatus: () => request('GET', '/engine/status', null, false),
  getHubAgents: (hubId) => request('GET', `/engine/hubs/${hubId}/agents`, null, false),
  getHubActions: (hubId, limit = 50) => request('GET', `/engine/hubs/${hubId}/actions?limit=${limit}`, null, false),
  getHubEvents: (hubId, limit = 50) => request('GET', `/engine/hubs/${hubId}/events?limit=${limit}`, null, false),
  spawnHubAgents: (hubId, hubName, topic) => request('POST', `/engine/hubs/${hubId}/spawn`, { hub_id: hubId, hub_name: hubName, topic }, false),
  retireHubAgents: (hubId) => request('DELETE', `/engine/hubs/${hubId}/agents`, null, false),
  pauseAgent: (agentId) => request('POST', `/engine/agents/${agentId}/pause`, null, false),
  resumeAgent: (agentId) => request('POST', `/engine/agents/${agentId}/resume`, null, false),
  pauseHub: (hubId) => request('POST', `/engine/hubs/${hubId}/pause`, null, false),
  resumeHub: (hubId) => request('POST', `/engine/hubs/${hubId}/resume`, null, false),
  stopHub: (hubId) => request('POST', `/engine/hubs/${hubId}/stop`, null, false),
  killHub: (hubId) => request('DELETE', `/engine/hubs/${hubId}/kill`, null, false),
  instructHub: (hubId, text, targetAgentId) => request('POST', `/engine/hubs/${hubId}/instruct`, { text, target_agent_id: targetAgentId }, false),
}
