import { AnimatePresence, MotionConfig, motion } from "framer-motion";
import { useEffect, type ReactNode } from "react";
import { Layout, NAV } from "./components/Layout";
import { ToastProvider } from "./components/Toast";
import { Button, Empty } from "./components/ui";
import { navigate, useLocation } from "./lib/router";
import { AudioPage } from "./pages/Audio";
import { AutoEdit } from "./pages/AutoEdit";
import { Dashboard } from "./pages/Dashboard";
import { EffectsPage } from "./pages/Effects";
import { Exports } from "./pages/Exports";
import { ImageStudio } from "./pages/ImageStudio";
import { Library } from "./pages/Library";
import { ProjectEditor } from "./pages/ProjectEditor";
import { Projects } from "./pages/Projects";
import { SettingsPage } from "./pages/Settings";

function NotFound() {
  return (
    <Empty title="Page not found">
      <Button className="mt-3" variant="primary" onClick={() => navigate("/")}>
        Back to the dashboard
      </Button>
    </Empty>
  );
}

function route(path: string): { key: string; node: ReactNode } {
  if (path === "/") return { key: "/", node: <Dashboard /> };
  if (path === "/auto-edit") return { key: path, node: <AutoEdit /> };
  if (path === "/image-studio") return { key: path, node: <ImageStudio /> };
  if (path === "/audio") return { key: path, node: <AudioPage /> };
  if (path === "/effects") return { key: path, node: <EffectsPage /> };
  if (path === "/projects") return { key: path, node: <Projects /> };
  const m = /^\/projects\/([\w-]+)$/.exec(path);
  if (m) return { key: path, node: <ProjectEditor id={m[1]} /> };
  if (path === "/library") return { key: path, node: <Library /> };
  if (path === "/exports") return { key: path, node: <Exports /> };
  if (path === "/settings") return { key: path, node: <SettingsPage /> };
  return { key: "404", node: <NotFound /> };
}

export function App() {
  const { path } = useLocation();
  const { key, node } = route(path);
  useEffect(() => {
    const item = NAV.find((n) => (n.to === "/" ? path === "/" : path.startsWith(n.to)));
    document.title = item && item.to !== "/" ? `${item.label} · CODM Beast Studio` : "CODM Beast Studio";
  }, [path]);
  return (
    <MotionConfig reducedMotion="user">
      <ToastProvider>
        <Layout>
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={key}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.18 }}
            >
              {node}
            </motion.div>
          </AnimatePresence>
        </Layout>
      </ToastProvider>
    </MotionConfig>
  );
}
