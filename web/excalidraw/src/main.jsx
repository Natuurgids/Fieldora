import React, { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { Excalidraw } from "@excalidraw/excalidraw";
import "@excalidraw/excalidraw/index.css";
import "./style.css";

window.EXCALIDRAW_ASSET_PATH = "./assets/";
window.EXCALIDRAW_EXPORT_SOURCE = "fieldora-offline";

const qtCall = (bridge, method, ...args) =>
  new Promise((resolve) => bridge[method](...args, resolve));

const connectBridge = () =>
  new Promise((resolve, reject) => {
    if (!window.qt?.webChannelTransport || !window.QWebChannel) {
      reject(new Error("Fieldora document bridge is unavailable"));
      return;
    }
    new window.QWebChannel(window.qt.webChannelTransport, (channel) => {
      resolve(channel.objects.fieldoraDocuments);
    });
  });

function FieldoraExcalidraw() {
  const [initialData, setInitialData] = useState(null);
  const [status, setStatus] = useState("Opening document…");
  const bridgeRef = useRef(null);
  const saveTimerRef = useRef(null);

  useEffect(() => {
    connectBridge()
      .then(async (connected) => {
        const payload = await qtCall(connected, "loadDocument");
        bridgeRef.current = connected;
        setInitialData(JSON.parse(payload));
        setStatus("Offline · saved in Fieldora Documents");
      })
      .catch((error) => setStatus(error.message));

    return () => {
      if (saveTimerRef.current !== null) {
        window.clearTimeout(saveTimerRef.current);
      }
    };
  }, []);

  const save = useCallback((elements, appState, files) => {
    const connected = bridgeRef.current;
    if (!connected) return;
    if (saveTimerRef.current !== null) {
      window.clearTimeout(saveTimerRef.current);
    }
    setStatus((current) =>
      current === "Unsaved changes…" ? current : "Unsaved changes…",
    );
    saveTimerRef.current = window.setTimeout(async () => {
      saveTimerRef.current = null;
      const payload = JSON.stringify({
        type: "excalidraw",
        version: 2,
        source: "fieldora-offline",
        elements,
        appState,
        files,
      });
      const result = await qtCall(connected, "saveDocument", payload);
      setStatus(result);
    }, 500);
  }, []);

  if (!initialData) {
    return <main className="loading">{status}</main>;
  }

  return (
    <main className="application">
      <div className="status" role="status">{status}</div>
      <div className="canvas">
        <Excalidraw
          initialData={initialData}
          onChange={save}
          autoFocus
          detectScroll
          handleKeyboardGlobally
          langCode="en"
          name="Fieldora Whiteboard"
        />
      </div>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<FieldoraExcalidraw />);
