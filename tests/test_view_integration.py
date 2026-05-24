"""End-to-end integration: route a request through real DRF view machinery.

Confirms that `FastSerializer` + `FastJSONRenderer` plug into the standard
DRF response cycle (content negotiation, render, finalize) without forks
or monkey-patches.
"""

import json

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from drf_fastserializers import FastJSONRenderer

from .conftest import TxnOut


class _ListView(APIView):
    permission_classes = [AllowAny]
    renderer_classes = [FastJSONRenderer]
    rows: list = []

    def get(self, request, *args, **kwargs):
        return Response(TxnOut.drf(instance=self.rows, many=True).data)


def test_view_returns_fast_payload_via_drf(txn_dicts: list[dict]):
    _ListView.rows = txn_dicts
    factory = APIRequestFactory()
    response = _ListView.as_view()(factory.get("/list/"))
    response.render()

    assert response.status_code == 200
    assert response["Content-Type"] == "application/json"
    body = json.loads(response.content)
    assert len(body) == len(txn_dicts)
    assert body[0]["id"] == 1


def test_view_response_data_dict_accessible(txn_dicts: list[dict]):
    """Tests + middleware sometimes touch `response.data` before render.
    The marker payload should lazy-materialize on subscript."""
    _ListView.rows = txn_dicts
    factory = APIRequestFactory()
    response = _ListView.as_view()(factory.get("/list/"))

    # access before render
    assert response.data[0]["id"] == 1
    assert response.data[0]["flags"]["is_refund"] is True


def test_view_renders_without_spaces_in_separator(txn_dicts: list[dict]):
    _ListView.rows = txn_dicts
    factory = APIRequestFactory()
    response = _ListView.as_view()(factory.get("/list/"))
    response.render()
    assert b": " not in response.content
