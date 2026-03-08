import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/select'
import { exportUrl } from '@/api/client'

type ExportFormat = 'csv' | 'json' | 'xlsx'

interface ExportPanelProps {
  surveyId: string
  startDate?: Date | null
  endDate?: Date | null
}

export function ExportPanel({ surveyId, startDate, endDate }: ExportPanelProps) {
  const [format, setFormat] = useState<ExportFormat>('csv')

  function handleDownload() {
    const url = exportUrl(surveyId, format, startDate, endDate)
    // Use window.location.href for file downloads — NOT fetch()
    window.location.href = url
  }

  return (
    <div className="flex items-end gap-3">
      <Select
        id="export-format"
        label="Export format"
        value={format}
        onChange={(e) => setFormat(e.target.value as ExportFormat)}
        className="w-32"
      >
        <option value="csv">CSV</option>
        <option value="json">JSON</option>
        <option value="xlsx">Excel (XLSX)</option>
      </Select>
      <Button variant="outline" onClick={handleDownload}>
        Download
      </Button>
    </div>
  )
}
