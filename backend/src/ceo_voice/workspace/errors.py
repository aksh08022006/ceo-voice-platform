"""Safe repository failures; database exceptions and payloads never cross this boundary."""

from ceo_voice.core.exceptions import ApplicationError


class WorkspaceNotFound(ApplicationError):
    code = "workspace_record_not_found"


class RevisionConflict(ApplicationError):
    code = "workflow_revision_conflict"


class WorkflowBusy(ApplicationError):
    code = "workflow_operation_pending"


class IdempotencyConflict(ApplicationError):
    code = "idempotency_key_conflict"


class LeaseConflict(ApplicationError):
    code = "model_run_lease_conflict"


class ApprovalConflict(ApplicationError):
    code = "workflow_approval_conflict"


class WorkspaceQuotaExceeded(ApplicationError):
    code = "workspace_model_run_quota_exceeded"
