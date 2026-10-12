import type { Hazard } from "../api/types";
import { fieldClass, labelClass } from "./formStyles";

const HAZARD_LABELS: Record<string, string> = { heatwave: "Heatwave" };

interface Props {
  hazards: string[];
  value: Hazard;
  onChange: (hazard: Hazard) => void;
}

/** Lists only the hazards the backend reports as implemented. */
export function HazardSelector({ hazards, value, onChange }: Props) {
  return (
    <div className="w-36">
      <label htmlFor="hazard" className={labelClass}>
        Hazard
      </label>
      <select
        id="hazard"
        className={fieldClass}
        value={value}
        onChange={(event) => onChange(event.target.value as Hazard)}
      >
        {hazards.map((hazard) => (
          <option key={hazard} value={hazard}>
            {HAZARD_LABELS[hazard] ?? hazard}
          </option>
        ))}
      </select>
    </div>
  );
}
