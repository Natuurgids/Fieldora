"""Response wrapper for WEB-041 Observation workspace action parity."""

from natureai_next.server.api import ApiResponse
from natureai_next.server.observation_actions_web import patch_observation_actions_response


class ObservationActionsApiMixin:
    """Apply Observation action-state alignment before the final WEB-040 audit."""

    def dispatch(
        self, method: str, target: str, headers: dict[str, str], body: bytes
    ) -> ApiResponse:
        response = super().dispatch(method, target, headers, body)
        return patch_observation_actions_response(target, response)
