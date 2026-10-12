import { AnimatePresence, motion } from "framer-motion";
import { Save, Undo2 } from "lucide-react";
import { Button } from "./ui";

/** Floating "unsaved changes" bar. */
export function SaveBar({
  dirty,
  saving,
  onSave,
  onDiscard,
  label = "Unsaved changes",
}: {
  dirty: boolean;
  saving: boolean;
  onSave: () => void;
  onDiscard?: () => void;
  label?: string;
}) {
  return (
    <AnimatePresence>
      {dirty && (
        <motion.div
          initial={{ y: 40, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 40, opacity: 0 }}
          className="fixed inset-x-3 bottom-20 z-40 mx-auto flex max-w-md items-center gap-2 rounded-2xl border border-cyber/40 bg-ink-850/95 p-2.5 pl-4 shadow-[0_0_40px_-10px_rgb(34_211_238/0.7)] backdrop-blur lg:bottom-6 lg:left-60"
          role="region"
          aria-label="Save changes"
        >
          <span className="flex-1 text-sm font-semibold text-ink-100">{label}</span>
          {onDiscard && (
            <Button size="sm" variant="ghost" onClick={onDiscard} icon={<Undo2 className="size-3.5" />}>
              Discard
            </Button>
          )}
          <Button size="sm" variant="primary" onClick={onSave} loading={saving} icon={<Save className="size-3.5" />}>
            Save
          </Button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
