import os
from typing import List, Set, Tuple, Union

from jinja2 import Environment, FileSystemLoader

import requests
import semver
import shutil


class Image:
    """Holds Docker image data for building."""

    def __init__(self, tags: Set[str], path: str):
        self.tags = tags
        self.path = path


class BuildData(object):
    """Defines an element of the build matrix."""

    def __init__(self, version: semver.VersionInfo, options: List[Union[str, type(None)]]):
        self.version = version
        self.options = options

    def get_formatted_version(self) -> str:
        return semver.format_version(*self.version)

    def filter_options(self) -> List[Union[str, type(None)]]:
        return [str(x) for x in self.options if x is not None]


class BuildMatrix:
    def __init__(self, data: Set[BuildData]):
        self.data = data

        latest = {}
        self.latest = {}

        # Find latest versions
        for d in data:
            major = d.version.major
            minor = "%s.%s" % (d.version.major, d.version.minor)
            version = d.get_formatted_version()

            if "prerelease" in version:
                major += "-" + version["prerelease"]
                minor += "-" + version["prerelease"]

            latest[major] = semver.max_ver(latest.get(major, '0.0.0'), version)
            latest[minor] = semver.max_ver(latest.get(minor, '0.0.0'), version)

        # Rehash latest versions
        for l, version in latest.items():
            if version not in self.latest:
                self.latest[version] = set()

            self.latest[version].add(l)

    def build(self, base_path: str, full_version_path: bool = False) -> Set[Tuple[BuildData, Image]]:
        images = set()

        for d in self.data:
            version = d.get_formatted_version()
            minor = "%s.%s" % (d.version.major, d.version.minor)
            versions = {version}
            path_version = minor

            if full_version_path:
                path_version = version

            if version in self.latest:
                versions = versions.union(self.latest[version])

            tags = set()

            for v in versions:
                tags.add('-'.join([str(x) for x in [v] + list(d.options) if x is not None]))

            path = os.path.join(base_path, '/'.join([str(x) for x in [path_version] + list(d.options) if x is not None]))

            images.add((d, Image(tags, path)))

        return images


def create_build_matrix(matrix: Set[Union[str, type(None)]]) -> BuildMatrix:
    data = set()

    for d in matrix:
        data.add(BuildData(semver.parse_version_info(d[0]), d[1:]))

    return BuildMatrix(data)


class DockerfileBuilder:
    """Builds a list of Dockerfiles from a matrix."""

    def __init__(self, clear: bool = True):
        self.clear = clear

    def build(self, images: Set[Tuple[BuildData, Image]], dist: str = 'dist', template: str = 'Dockerfile.template'):
        env = Environment(loader=FileSystemLoader(os.path.dirname(os.path.realpath(template))))

        dist = os.path.realpath(dist)

        # Clear directory if exists
        if self.clear and os.path.isdir(dist):
            shutil.rmtree(dist)
        os.mkdir(dist)

        # Initialize template
        template = env.get_template(template)

        for data, image in images:
            dockerfile = image.path + "/Dockerfile"

            os.makedirs(image.path, exist_ok=True)

            template.stream(
                data=data,
                image=image
            ).dump(dockerfile)


class HubUpdater:
    """Updates Docker Hub"""

    API_URL = "https://hub.docker.com/v2"
    token = None

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password

    def login(self):
        url = self.API_URL + "/users/login/"
        response = requests.post(url, data={"username": self.username, "password": self.password})

        if response.status_code == 200:
            body = response.json()

            self.token = body["token"]
        else:
            raise Exception("Cannot login to Docker HUB")

    def clear_builds(self, repo: str):
        if self.token is None:
            raise Exception("You need to login first")

        headers = {"Authorization": "JWT " + self.token}
        builds = []

        response = requests.get(self.API_URL + "/repositories/%s/autobuild/tags/" % repo, headers=headers)

        if response.status_code == 200:
            body = response.json()
            builds.extend(body["results"])

            while not (body["next"] is None):
                response = requests.get(body["next"], headers=headers)

                if response.status_code == 200:
                    body = response.json()
                    builds.extend(body["results"])
                else:
                    raise Exception("Invalid response")
        else:
            raise Exception("Invalid response")

        for build in builds:
            response = requests.delete(self.API_URL + "/repositories/%s/autobuild/tags/%s/" % (repo, build["id"]),
                                       headers=headers)

            if response.status_code != 204:
                raise Exception("ERROR [%d]: %s" % (response.status_code, response.text))

    def add_builds(self, repo: str, branch: str, images: Set[Tuple[BuildData, Image]]):
        if self.token is None:
            raise Exception("You need to login first")

        headers = {"Authorization": "JWT " + self.token}

        for build_element, image in images:
            for tag in image.tags:
                build = {"name": tag, "dockerfile_location": image.path, "source_name": branch, "source_type": "Branch",
                         "isNew": True}

                response = requests.post(self.API_URL + "/repositories/%s/autobuild/tags/" % repo, headers=headers, data=build)

                if response.status_code != 201:
                    raise Exception("ERROR [%d]: %s" % (response.status_code, response.text))
