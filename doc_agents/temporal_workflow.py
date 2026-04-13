from __future__ import annotations

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from .activities import (
        ChunkInput,
        ExtractInput,
        ParseDocumentInput,
        SynthesisInput,
        ValidationInput,
        extract_business_rules_activity,
        extract_data_schema_activity,
        extract_tables_activity,
        extract_workflows_activity,
        generate_frontmatter_activity,
        parse_docx_activity,
        persist_markdown_activity,
        render_mermaid_activity,
        semantic_chunk_activity,
        synthesize_markdown_activity,
        validate_markdown_against_chunks_activity,
        vision_extract_activity,
    )
    from .models import ReviewTarget
    from .temporal_contract import WORKFLOW_NAME
    from .temporal_payloads import (
        ArtifactReviewUpdatePayload,
        ReviewSubmission,
        WorkflowSnapshot,
        WorkflowStartInput,
    )
    from .workflow import DocumentWorkflowState, WorkflowStatus


ACTIVITY_TIMEOUT = timedelta(seconds=30)


@workflow.defn(name=WORKFLOW_NAME)
class TemporalDocumentWorkflow:
    def __init__(self) -> None:
        self._state: DocumentWorkflowState | None = None
        self._pending_ir_review: ReviewSubmission | None = None
        self._pending_final_review: ReviewSubmission | None = None

    @workflow.run
    async def run(self, payload: WorkflowStartInput) -> WorkflowSnapshot:
        self._state = DocumentWorkflowState.start(
            document_id=payload.document_id,
            source_uri=payload.source_uri,
        )
        source_input = ParseDocumentInput(
            document_id=payload.document_id,
            source_uri=payload.source_uri,
        )
        parsed_document = await workflow.execute_activity(
            parse_docx_activity,
            source_input,
            schedule_to_close_timeout=ACTIVITY_TIMEOUT,
        )
        await workflow.execute_activity(
            extract_tables_activity,
            source_input,
            schedule_to_close_timeout=ACTIVITY_TIMEOUT,
        )
        if payload.enable_vision:
            await workflow.execute_activity(
                vision_extract_activity,
                source_input,
                schedule_to_close_timeout=ACTIVITY_TIMEOUT,
            )
        chunk_set = await workflow.execute_activity(
            semantic_chunk_activity,
            ChunkInput(document_id=payload.document_id, parsed_document=parsed_document),
            schedule_to_close_timeout=ACTIVITY_TIMEOUT,
        )
        self._state.record_chunk_set(chunk_set)

        while True:
            await self._run_extraction(payload.document_id, chunk_set)
            await workflow.wait_condition(
                lambda: self._pending_ir_review is not None
                or (
                    self._state is not None
                    and self._state.status == WorkflowStatus.SYNTHESIS_READY
                )
            )
            if self._pending_ir_review is not None:
                ir_review = self._pending_ir_review
                self._pending_ir_review = None
                self._state.apply_ir_review(ir_review.to_core_decision())
            if self._state.status == WorkflowStatus.SYNTHESIS_READY:
                break

        while True:
            markdown_draft = await self._run_synthesis(payload.document_id)
            report = await workflow.execute_activity(
                validate_markdown_against_chunks_activity,
                ValidationInput(
                    document_id=payload.document_id,
                    markdown_draft=markdown_draft,
                    chunk_set=chunk_set,
                ),
                schedule_to_close_timeout=ACTIVITY_TIMEOUT,
            )
            self._state.status = WorkflowStatus.WAITING_FOR_FINAL_REVIEW
            if not report.passed:
                self._state.next_actions = ["rerun:synthesis"]
            await workflow.wait_condition(lambda: self._pending_final_review is not None)
            final_review = self._pending_final_review
            self._pending_final_review = None
            assert final_review is not None
            decision = final_review.to_core_decision()
            self._state.apply_final_review(decision)
            if decision.action == "approve":
                self._state.status = WorkflowStatus.COMPLETED
                return self.snapshot()
            await self._apply_reruns(payload.document_id, chunk_set)

    async def _run_extraction(self, document_id: str, chunk_set) -> None:
        data_schema = await workflow.execute_activity(
            extract_data_schema_activity,
            ExtractInput(document_id=document_id, chunk_set=chunk_set),
            schedule_to_close_timeout=ACTIVITY_TIMEOUT,
        )
        business_rules = await workflow.execute_activity(
            extract_business_rules_activity,
            ExtractInput(document_id=document_id, chunk_set=chunk_set),
            schedule_to_close_timeout=ACTIVITY_TIMEOUT,
        )
        workflows_json = await workflow.execute_activity(
            extract_workflows_activity,
            ExtractInput(document_id=document_id, chunk_set=chunk_set),
            schedule_to_close_timeout=ACTIVITY_TIMEOUT,
        )
        assert self._state is not None
        self._state.record_extraction_outputs(
            data_schema=data_schema,
            business_rules=business_rules,
            workflows=workflows_json,
        )

    async def _run_synthesis(self, document_id: str):
        assert self._state is not None
        synthesis_input = SynthesisInput(
            document_id=document_id,
            data_schema=self._state.artifacts["data_schema_json"],
            business_rules=self._state.artifacts["business_rules_json"],
            workflows=self._state.artifacts["workflows_json"],
        )
        await workflow.execute_activity(
            render_mermaid_activity,
            synthesis_input,
            schedule_to_close_timeout=ACTIVITY_TIMEOUT,
        )
        await workflow.execute_activity(
            generate_frontmatter_activity,
            synthesis_input,
            schedule_to_close_timeout=ACTIVITY_TIMEOUT,
        )
        markdown_draft = await workflow.execute_activity(
            synthesize_markdown_activity,
            synthesis_input,
            schedule_to_close_timeout=ACTIVITY_TIMEOUT,
        )
        persisted_markdown = await workflow.execute_activity(
            persist_markdown_activity,
            markdown_draft,
            schedule_to_close_timeout=ACTIVITY_TIMEOUT,
        )
        self._state.artifacts["markdown_draft"] = persisted_markdown
        return persisted_markdown

    async def _apply_reruns(self, document_id: str, chunk_set) -> None:
        assert self._state is not None
        for action in self._state.next_actions:
            if action == "rerun:extract_data_schema":
                self._state.artifacts["data_schema_json"] = await workflow.execute_activity(
                    extract_data_schema_activity,
                    ExtractInput(document_id=document_id, chunk_set=chunk_set),
                    schedule_to_close_timeout=ACTIVITY_TIMEOUT,
                )
            elif action == "rerun:extract_business_rules":
                self._state.artifacts["business_rules_json"] = await workflow.execute_activity(
                    extract_business_rules_activity,
                    ExtractInput(document_id=document_id, chunk_set=chunk_set),
                    schedule_to_close_timeout=ACTIVITY_TIMEOUT,
                )
            elif action == "rerun:extract_workflows":
                self._state.artifacts["workflows_json"] = await workflow.execute_activity(
                    extract_workflows_activity,
                    ExtractInput(document_id=document_id, chunk_set=chunk_set),
                    schedule_to_close_timeout=ACTIVITY_TIMEOUT,
                )
            elif action == "rerun:synthesis":
                await self._run_synthesis(document_id)
        self._state.next_actions.clear()

    @workflow.signal(name="ir_review_submitted")
    def submit_ir_review(self, submission: ReviewSubmission) -> None:
        self._pending_ir_review = submission

    @workflow.signal(name="ir_artifact_updated")
    def submit_ir_artifact_update(self, update: ArtifactReviewUpdatePayload) -> None:
        assert self._state is not None
        core_update = update.to_core_update()
        self._state.apply_ir_artifact_update(core_update.target, core_update.artifact)

    @workflow.signal(name="final_review_submitted")
    def submit_final_review(self, submission: ReviewSubmission) -> None:
        self._pending_final_review = submission

    @workflow.query
    def current_status(self) -> str:
        if self._state is None:
            return WorkflowStatus.CREATED.value
        return self._state.status.value

    @workflow.query
    def pending_actions(self) -> list[str]:
        if self._state is None:
            return []
        return list(self._state.next_actions)

    @workflow.query
    def snapshot(self) -> WorkflowSnapshot:
        if self._state is None:
            return WorkflowSnapshot(
                document_id="",
                status=WorkflowStatus.CREATED.value,
                next_actions=[],
                artifact_versions={},
            )
        return WorkflowSnapshot(
            document_id=self._state.document_id,
            status=self._state.status.value,
            next_actions=list(self._state.next_actions),
            artifact_versions=self._state.artifact_versions,
        )
