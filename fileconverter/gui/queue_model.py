"""Table model over the job queue: one row per job."""

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt

from ..queue import FINISHED, Job, JobQueue, JobState

COL_FILE, COL_PRESET, COL_STATUS, COL_ACTIONS = range(4)


def status_text(job: Job) -> str:
    match job.state:
        case JobState.PENDING:
            return "Ready"
        case JobState.WAITING:
            return "Waiting"
        case JobState.RUNNING:
            return f"{int(job.progress * 100)}%" if job.progress is not None else "Converting…"
        case JobState.DONE:
            return "Done"
        case JobState.FAILED:
            return "Failed"
        case JobState.CANCELLED:
            return "Cancelled"
        case JobState.SKIPPED:
            return "Skipped (file exists)"


class QueueModel(QAbstractTableModel):
    HEADERS = ("File", "Convert to", "Status", "")

    def __init__(self, queue: JobQueue, parent: QObject | None = None):
        super().__init__(parent)
        self.queue = queue
        self._ids = [j.id for j in queue.jobs()]
        queue.job_added.connect(self._added)
        queue.job_removed.connect(self._removed)
        queue.job_changed.connect(self._changed)

    def job_id(self, row: int) -> int:
        return self._ids[row]

    def row_of(self, job_id: int) -> int:
        return self._ids.index(job_id)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._ids)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        flags = super().flags(index)
        if index.column() == COL_PRESET:
            job = self.queue.job(self.job_id(index.row()))
            if job.state in (JobState.PENDING, JobState.WAITING, *FINISHED):
                flags |= Qt.ItemIsEditable
        return flags

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        job = self.queue.job(self.job_id(index.row()))
        col = index.column()
        if role == Qt.DisplayRole:
            return {COL_FILE: job.src.name, COL_PRESET: job.preset.name,
                    COL_STATUS: status_text(job)}.get(col)
        if role == Qt.ToolTipRole:
            if col == COL_FILE:
                return str(job.src)
            if col == COL_STATUS and job.state is JobState.FAILED:
                return job.error
            if col == COL_STATUS and job.outputs:
                return "\n".join([str(p) for p in job.outputs] + [job.warning] * bool(job.warning))
        if role == Qt.UserRole and col == COL_STATUS:
            return job.progress
        return None

    def _added(self, job_id: int) -> None:
        row = len(self._ids)
        self.beginInsertRows(QModelIndex(), row, row)
        self._ids.append(job_id)
        self.endInsertRows()

    def _removed(self, job_id: int) -> None:
        row = self.row_of(job_id)
        self.beginRemoveRows(QModelIndex(), row, row)
        del self._ids[row]
        self.endRemoveRows()

    def _changed(self, job_id: int) -> None:
        row = self.row_of(job_id)
        self.dataChanged.emit(self.index(row, 0), self.index(row, COL_ACTIONS))
