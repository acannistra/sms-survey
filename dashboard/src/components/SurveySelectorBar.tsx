import { Select } from '@/components/ui/select'
import type { SurveyListItem } from '@/api/types'

interface SurveySelectorBarProps {
  surveys: SurveyListItem[]
  selectedId: string | null
  onChange: (id: string) => void
  isLoading?: boolean
}

export function SurveySelectorBar({
  surveys,
  selectedId,
  onChange,
  isLoading,
}: SurveySelectorBarProps) {
  return (
    <div className="flex items-center gap-3">
      <Select
        id="survey-selector"
        label="Survey"
        value={selectedId ?? ''}
        onChange={(e) => onChange(e.target.value)}
        disabled={isLoading}
        className="min-w-[220px]"
      >
        <option value="" disabled>
          {isLoading ? 'Loading surveys…' : 'Select a survey'}
        </option>
        {surveys.map((s) => (
          <option key={s.survey_id} value={s.survey_id}>
            {s.name} (v{s.version})
          </option>
        ))}
      </Select>
    </div>
  )
}
