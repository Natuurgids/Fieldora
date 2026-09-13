(() => {
  "use strict";

  const params = new URLSearchParams(window.location.search);
  let projectId = params.get("project_id") || "";
  let boardId = params.get("board_id") || "";
  let revision = 0;
  let lastLocalSaveAt = 0;
  let pollTimer = null;

  const token = () => window.sessionStorage.getItem("fieldora-session") || "";

  async function api(path, options = {}) {
    const headers = {
      ...(options.headers || {}),
      "X-Fieldora-Purpose": "research",
    };
    const currentToken = token();
    if (!currentToken) {
      throw new Error("Sign in to Fieldora before opening a whiteboard");
    }
    headers.Authorization = `Bearer ${currentToken}`;
    if (options.body !== undefined) {
      headers["Content-Type"] = "application/json";
    }
    const response = await fetch(path, { ...options, headers });
    let payload = null;
    if (response.status !== 204) {
      const type = response.headers.get("content-type") || "";
      payload = type.includes("json") ? await response.json() : await response.text();
    }
    if (!response.ok) {
      const error = new Error(payload?.error || `Fieldora request failed (${response.status})`);
      error.status = response.status;
      throw error;
    }
    return payload;
  }

  function emptyDocument() {
    return {
      type: "excalidraw",
      version: 2,
      source: "fieldora-web",
      elements: [],
      appState: {},
      files: {},
    };
  }

  function sceneToDocument(scene) {
    return {
      type: "excalidraw",
      version: 2,
      source: "fieldora-web",
      elements: scene?.elements || [],
      appState: scene?.appState || {},
      files: scene?.files || {},
    };
  }

  async function ensureBoard() {
    if (!projectId) {
      throw new Error("Open the whiteboard from a Fieldora project");
    }
    if (boardId) {
      const result = await api(`/api/v1/excalidraw/boards/${encodeURIComponent(boardId)}`);
      revision = Number(result.revision || result.item?.revision || 0);
      return result.item;
    }
    const title = params.get("title") || "Whiteboard";
    const result = await api("/api/v1/excalidraw/boards", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, title, scene: emptyDocument() }),
    });
    boardId = result.item.id;
    revision = Number(result.revision || result.item.revision || 1);
    const updated = new URL(window.location.href);
    updated.searchParams.set("project_id", projectId);
    updated.searchParams.set("board_id", boardId);
    window.history.replaceState(null, "", updated);
    return result.item;
  }

  async function loadDocument() {
    const board = await ensureBoard();
    startPolling();
    return JSON.stringify(sceneToDocument(board.scene));
  }

  async function saveDocument(raw) {
    const parsed = JSON.parse(raw);
    if (!boardId) {
      await ensureBoard();
    }
    try {
      const result = await api(`/api/v1/excalidraw/boards/${encodeURIComponent(boardId)}`, {
        method: "PUT",
        headers: { "If-Match": String(revision) },
        body: JSON.stringify({
          scene: {
            elements: parsed.elements || [],
            appState: parsed.appState || {},
            files: parsed.files || {},
          },
        }),
      });
      revision = Number(result.revision || result.item?.revision || revision + 1);
      lastLocalSaveAt = Date.now();
      return `Saved in Fieldora · revision ${revision}`;
    } catch (error) {
      if (error.status === 409) {
        return "Another Fieldora user saved a newer revision · reloading…";
      }
      throw error;
    }
  }

  async function poll() {
    if (!boardId || !token()) return;
    try {
      const result = await api(
        `/api/v1/excalidraw/boards/${encodeURIComponent(boardId)}/collaboration?since=${revision}`,
      );
      if (!result.changed) return;
      const remoteRevision = Number(result.revision || 0);
      if (remoteRevision <= revision) return;
      // The desktop-compatible Excalidraw bundle exposes only load/save through
      // QWebChannel. A controlled reload is therefore the safe synchronization
      // boundary until the bundle's web adapter can call updateScene directly.
      if (Date.now() - lastLocalSaveAt > 1500) {
        revision = remoteRevision;
        window.location.reload();
      }
    } catch (error) {
      // Authentication/authorization failures remain terminal at the API boundary.
      if (error.status === 401 || error.status === 403) {
        window.clearInterval(pollTimer);
        pollTimer = null;
      }
    }
  }

  function startPolling() {
    if (pollTimer !== null) return;
    pollTimer = window.setInterval(poll, 2000);
  }

  const bridge = {
    loadDocument(callback) {
      loadDocument()
        .then((payload) => callback(payload))
        .catch((error) => callback(JSON.stringify({ ...emptyDocument(), error: error.message })));
    },
    saveDocument(payload, callback) {
      saveDocument(payload)
        .then((status) => {
          callback(status);
          if (status.includes("reloading")) {
            window.setTimeout(() => window.location.reload(), 500);
          }
        })
        .catch((error) => callback(`Save failed: ${error.message}`));
    },
  };

  // Compatibility shim for the existing desktop bundle. No Qt transport leaves
  // the browser and no external collaboration service is contacted.
  window.qt = { webChannelTransport: { fieldoraWebBridge: true } };
  window.QWebChannel = function QWebChannel(_transport, callback) {
    callback({ objects: { fieldoraDocuments: bridge } });
  };
})();
