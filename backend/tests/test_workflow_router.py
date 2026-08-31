import pytest

from app.workflows import ExplicitWorkflowRouter, WorkflowKind


def test_explicit_workflow_router_accepts_report_generation_inputs():
    decision = ExplicitWorkflowRouter().route(
        "report_generation",
        template_filename="template.docx",
        data_filename="data.xlsx",
        instruction="生成经营分析报告",
    )
    assert decision.workflow is WorkflowKind.REPORT_GENERATION
    assert decision.confidence == 1.0


@pytest.mark.parametrize(
    ("workflow", "template", "data", "instruction"),
    [
        ("conversation", "template.docx", "data.xlsx", "生成报告"),
        ("report_generation", "template.pdf", "data.xlsx", "生成报告"),
        ("report_generation", "template.docx", "data.csv", "生成报告"),
        ("report_generation", "template.docx", "data.xlsx", "  "),
    ],
)
def test_explicit_workflow_router_rejects_invalid_inputs(workflow, template, data, instruction):
    with pytest.raises(ValueError):
        ExplicitWorkflowRouter().route(
            workflow,
            template_filename=template,
            data_filename=data,
            instruction=instruction,
        )
