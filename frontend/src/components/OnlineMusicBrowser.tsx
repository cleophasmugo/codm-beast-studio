import { Check, ExternalLink, Globe, Plus, Search } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { api, type Media, type OnlineTrack } from "../api";
import { formatDuration } from "../lib/format";
import { useToast } from "./Toast";
import { Badge, Button, Card, CardTitle, Empty, ErrorBanner, Note, Spinner } from "./ui";

const QUICK_SEARCHES = ["Epic", "Electronic", "Hip hop", "Rock", "Dubstep", "Cinematic", "Trap", "Gaming"];

/** Search free-licensed music online (Jamendo via Openverse) and add tracks to the user's music. */
export function OnlineMusicBrowser({ onImported }: { onImported: (m: Media) => void }) {
  const toast = useToast();
  const [query, setQuery] = useState("");
  const [searched, setSearched] = useState("");
  const [results, setResults] = useState<OnlineTrack[]>([]);
  const [page, setPage] = useState(1);
  const [pageCount, setPageCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState<string | null>(null);
  const seq = useRef(0);

  const run = useCallback(async (q: string, p = 1) => {
    const id = ++seq.current;
    setLoading(true);
    setError(null);
    try {
      const res = await api.searchMusic(q, p);
      if (id !== seq.current) return;
      setResults((prev) => (p === 1 ? res.results : [...prev, ...res.results]));
      setPage(p);
      setPageCount(res.page_count);
      setSearched(q);
    } catch (e) {
      if (id === seq.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (id === seq.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void run("gaming");
  }, [run]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void run(query.trim());
  };

  const add = async (t: OnlineTrack) => {
    setAdding(t.id);
    try {
      const m = await api.importMusic(t.id);
      setResults((prev) => prev.map((x) => (x.id === t.id ? { ...x, imported_media_id: m.id } : x)));
      onImported(m);
      toast.success(`Added "${t.title}" to your music`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e));
    } finally {
      setAdding(null);
    }
  };

  return (
    <Card>
      <CardTitle icon={<Globe className="size-4" />}>Browse music online</CardTitle>
      <form onSubmit={submit} className="flex gap-2" role="search">
        <input
          className="field flex-1"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by mood, genre or artist"
          aria-label="Search online music"
          maxLength={200}
        />
        <Button type="submit" variant="primary" icon={<Search className="size-4" />} loading={loading && page === 1}>
          Search
        </Button>
      </form>
      <div className="mt-3 flex flex-wrap gap-1.5">
        {QUICK_SEARCHES.map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => {
              setQuery(q);
              void run(q);
            }}
            className="rounded-full border border-white/10 px-2.5 py-1 text-xs text-ink-200 transition hover:border-cyber/50 hover:text-white"
          >
            {q}
          </button>
        ))}
      </div>
      <div className="mt-3">
        <Note>
          Free tracks from Jamendo that allow use in videos (CC0, CC BY, CC BY-SA). Credit the artist in your video
          description: the credit line is saved with each track you add.
        </Note>
      </div>

      <div className="mt-4 space-y-3">
        {error && <ErrorBanner onRetry={() => void run(searched || query, 1)}>{error}</ErrorBanner>}
        {loading && !results.length && <Spinner label="Searching" />}
        {!loading && !error && !results.length && (
          <Empty title="No tracks found">Try another word, like a genre or a mood.</Empty>
        )}
        {results.map((t) => (
          <div key={t.id} className="rounded-xl border border-white/[0.08] bg-ink-900/60 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold text-white">{t.title}</p>
                <p className="truncate text-xs text-ink-300">{t.creator}</p>
              </div>
              <Badge tone="green">{t.license}</Badge>
              <Badge>{formatDuration(t.duration)}</Badge>
              {t.imported_media_id ? (
                <Button size="sm" variant="ghost" disabled icon={<Check className="size-3.5" />}>
                  Added
                </Button>
              ) : (
                <Button
                  size="sm"
                  variant="success"
                  loading={adding === t.id}
                  disabled={adding !== null && adding !== t.id}
                  onClick={() => void add(t)}
                  icon={<Plus className="size-3.5" />}
                >
                  Add to my music
                </Button>
              )}
            </div>
            {t.genres.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {t.genres.map((g) => (
                  <Badge key={g} tone="violet">
                    {g}
                  </Badge>
                ))}
              </div>
            )}
            <audio controls preload="none" src={t.preview_url} className="mt-2 h-9 w-full" aria-label={`Preview ${t.title}`} />
            {t.page_url && (
              <a
                href={t.page_url}
                target="_blank"
                rel="noreferrer noopener"
                className="mt-1.5 inline-flex items-center gap-1 text-[11px] text-ink-400 hover:text-cyber"
              >
                View on Jamendo <ExternalLink className="size-3" aria-hidden />
              </a>
            )}
          </div>
        ))}
        {results.length > 0 && page < pageCount && (
          <Button variant="secondary" className="w-full" loading={loading} onClick={() => void run(searched, page + 1)}>
            Load more
          </Button>
        )}
      </div>
    </Card>
  );
}
