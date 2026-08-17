import re
import typing

import fastapi
import starlette.datastructures
import starlette.requests
import uvicorn

from book_converter.presentation import api

_PARAM_PATTERN = re.compile(r"\{(\w+)\}")


class FastApiApplication:
    def __init__(self) -> None:
        self._app = fastapi.FastAPI()

    def add_route(self, route: api.Route) -> typing.Self:
        param_names = _PARAM_PATTERN.findall(route.rule)
        self._app.add_api_route(
            route.rule, _endpoint(route.handler, param_names), methods=[route.method]
        )
        return self

    def add_routes(self, routes: list[api.Route]) -> typing.Self:
        for route in routes:
            self.add_route(route)
        return self

    def listen(self, port: int) -> None:
        uvicorn.run(self._app, host="0.0.0.0", port=port)


def _endpoint(
    handler: api.Handler, param_names: list[str]
) -> typing.Callable[[starlette.requests.Request], typing.Awaitable[fastapi.Response]]:
    async def endpoint(request: starlette.requests.Request) -> fastapi.Response:
        generic_request = await _to_generic_request(request, param_names)
        response = handler(generic_request)
        return fastapi.Response(
            content=response.body,
            status_code=response.status_code,
            headers=response.headers,
        )

    return endpoint


async def _to_generic_request(
    request: starlette.requests.Request, param_names: list[str]
) -> api.Request:
    form: dict[str, list[str]] = {}
    files: dict[str, list[typing.IO]] = {}

    content_type = request.headers.get("content-type", "")
    if content_type.startswith(("multipart/form-data", "application/x-www-form-urlencoded")):
        form_data = await request.form()
        for key in form_data:
            for value in form_data.getlist(key):
                if isinstance(value, starlette.datastructures.UploadFile):
                    files.setdefault(key, []).append(value.file)
                else:
                    form.setdefault(key, []).append(value)

    return api.Request(
        path=request.url.path,
        method=typing.cast(api.Method, request.method),
        content=await request.body(),
        params=[request.path_params[name] for name in param_names],
        query={key: request.query_params.getlist(key) for key in request.query_params},
        headers=dict(request.headers),
        files=files,
        form=form,
    )
