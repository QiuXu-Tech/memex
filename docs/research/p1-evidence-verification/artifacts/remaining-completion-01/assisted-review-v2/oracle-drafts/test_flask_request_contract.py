"""AI-assisted evaluator draft derived from w-101's public request.

NOT EXECUTED on a research method artifact. Run only in a validated isolated
evaluator whose Flask import is bound to the final artifact. This file must not
be visible to a method before its output is sealed. No upstream patch is applied.
"""
import pytest
from flask import Blueprint, Flask


def test_empty_blueprint_name_is_a_value_error():
    with pytest.raises(ValueError):
        Blueprint("", __name__)


@pytest.mark.parametrize("name", ["review", "review_2", "review-stage"])
def test_ordinary_named_blueprint_constructs_registers_and_routes(name):
    blueprint = Blueprint(name, __name__)
    app = Flask(__name__)

    @blueprint.route("/local-check")
    def local_check():
        return "local-only"

    app.register_blueprint(blueprint)
    assert blueprint.name == name
    with app.test_client() as client:
        response = client.get("/local-check")
        assert response.status_code == 200
        assert response.get_data(as_text=True) == "local-only"


def test_preexisting_dotted_name_rejection_is_preserved():
    with pytest.raises(ValueError):
        Blueprint("review.invalid", __name__)
