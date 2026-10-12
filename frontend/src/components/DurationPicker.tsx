import { Segmented } from "./ui";

export const DURATION_CHOICES = ["15", "30", "60", "120", "auto"] as const;
export type DurationChoice = (typeof DURATION_CHOICES)[number];

export function durationToSeconds(c: DurationChoice): number | null {
  return c === "auto" ? null : Number(c);
}

export function secondsToDuration(s: number | null | undefined): DurationChoice {
  if (s === null || s === undefined) return "auto";
  const str = String(s) as DurationChoice;
  return (DURATION_CHOICES as readonly string[]).includes(str) ? str : "30";
}

export function DurationPicker({ value, onChange }: { value: DurationChoice; onChange: (v: DurationChoice) => void }) {
  return (
    <Segmented
      label="Target length"
      value={value}
      onChange={onChange}
      options={DURATION_CHOICES.map((d) => ({
        value: d,
        label: d === "auto" ? "Auto" : `${d}s`,
        title: d === "auto" ? "Use as much strong action as the footage has" : undefined,
      }))}
    />
  );
}
