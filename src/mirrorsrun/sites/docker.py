import logging

import httpx
from starlette.requests import Request
from starlette.responses import Response

from mirrorsrun.docker_utils import get_docker_token
from mirrorsrun.proxy.direct import direct_proxy
from mirrorsrun.proxy.file_cache import try_file_based_cache
from mirrorsrun.sites.k8s import try_extract_image_name

logger = logging.getLogger(__name__)

BASE_URL = "https://registry-1.docker.io"


def inject_token(name: str, req: Request, httpx_req: httpx.Request):
    docker_token = get_docker_token(f"{name}")
    httpx_req.headers["Authorization"] = f"Bearer {docker_token}"
    return httpx_req


async def post_process(request: Request, response: Response):
    if response.status_code == 307:
        location = response.headers["location"]
        return await try_file_based_cache(request, location)

    return response


async def docker(request: Request):
    path = request.url.path
    if not path.startswith("/v2/"):
        return Response(content="Not Found", status_code=404)

    if path == "/v2/":
        return Response(content="OK")
        # return await direct_proxy(request, BASE_URL + '/v2/')

    name, resource, reference = try_extract_image_name(path)

    if not name:
        return Response(content="404 Not Found", status_code=404)

    # support docker pull xxx which name without library
    if "/" not in name:
        name = f"library/{name}"

    target_url = BASE_URL + f"/v2/{name}/{resource}/{reference}"

    logger.info(
        f"got docker request, {path=} {name=} {resource=} {reference=} {target_url=}"
    )

    return await direct_proxy(
        request,
        target_url,
        pre_process=lambda req, http_req: inject_token(name, req, http_req),
        post_process=post_process,  # cache in post_process
    )
