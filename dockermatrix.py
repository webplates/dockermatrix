import os
from typing import List, Set, Tuple, Dict

from jinja2 import Environment, FileSystemLoader
from collections import OrderedDict

import json
import requests
import semver
import shutil
import getpass
import sys


def __semver_format_major_version(version_info: semver.VersionInfo) -> str:
    version = str(version_info.major)

    if version_info.prerelease is not None:
        version += "-%s" % version_info.prerelease

    if version_info.build is not None:
        version += "+%s" % version_info.build

    return version


semver.format_major_version = __semver_format_major_version


def __semver_format_minor_version(version_info: semver.VersionInfo) -> str:
    version = "%d.%d" % (version_info.major, version_info.minor)

    if version_info.prerelease is not None:
        version += "-%s" % version_info.prerelease

    if version_info.build is not None:
        version += "+%s" % version_info.build

    return version


semver.format_minor_version = __semver_format_minor_version


class Image:
    """Holds Docker image data for building."""

    def __init__(self, tags: Set[str], path: str):
        self.tags = tags
        self.path = path


class ImageBuild(object):
    """Defines an element of the build matrix."""

    def __init__(self, version: semver.VersionInfo, options: Tuple):
        self.version = version
        self.options = options

    def get_formatted_version(self) -> str:
        return semver.format_version(*self.version)

    def filter_options(self) -> List[str]:
        return [str(x) for x in self.options if x is not None]


class BuildMatrix:
    def __init__(self, builds: Set[ImageBuild]):
        self.builds = builds

        latest = {}
        self.latest = {}

        # Find latest versions
        for build in builds:
            major = semver.format_major_version(build.version)
            minor = semver.format_minor_version(build.version)
            version = build.get_formatted_version()

            latest[major] = semver.max_ver(latest.get(major, "0.0.0"), version)
            latest[minor] = semver.max_ver(latest.get(minor, "0.0.0"), version)

        # Rehash latest versions
        for l, version in latest.items():
            if version not in self.latest:
                self.latest[version] = set()

            self.latest[version].add(l)

    def build(self, base_path: str, full_version_path: bool = False) -> Set[Tuple[ImageBuild, Image]]:
        images = set()

        for build in self.builds:
            version = build.get_formatted_version()
            minor = "%s.%s" % (build.version.major, build.version.minor)
            versions = {version}
            path_version = minor

            if full_version_path:
                path_version = version

            if version in self.latest:
                versions = versions.union(self.latest[version])

            tags = set()

            for v in versions:
                tags.add("-".join([str(x) for x in [v] + list(build.options) if x is not None]))

            path = os.path.join(base_path,
                                "/".join([str(x) for x in [path_version] + list(build.options) if x is not None]))

            images.add((build, Image(tags, path)))

        return images


def create_build_matrix(matrix: Set[Tuple[str, Tuple]]) -> BuildMatrix:
    builds = set()

    for build in matrix:
        builds.add(ImageBuild(semver.parse_version_info(build[0]), build[1]))

    return BuildMatrix(builds)


class Builder:
    """Builds a list of Dockerfiles and an image list from a matrix."""

    def __init__(self, clear: bool = True):
        self.clear = clear

    def build(self, images: Set[Tuple[ImageBuild, Image]], repo: str, branch: str, dist: str = "dist",
              template: str = "Dockerfile.template"):
        env = Environment(loader=FileSystemLoader(os.path.dirname(os.path.realpath(template))))

        dist = os.path.realpath(dist)

        # Clear directory if exists
        if self.clear and os.path.isdir(dist):
            shutil.rmtree(dist)
        os.mkdir(dist)

        # Initialize template
        template = env.get_template(template)

        image_list = OrderedDict()
        image_list["repo"] = repo
        image_list["branch"] = branch
        image_list["images"] = []

        for build, image in images:
            dockerfile = image.path + "/Dockerfile"

            os.makedirs(image.path, exist_ok=True)

            image_list_entry = OrderedDict()
            image_list_entry["tags"] = list(image.tags)
            image_list_entry["path"] = image.path
            image_list["images"].append(image_list_entry)

            template.stream(
                build=build,
                image=image
            ).dump(dockerfile)

        with open(os.path.join(dist, "images.json"), "w") as image_list_file:
            image_list_file.truncate()
            image_list_file.write(json.dumps(image_list, indent=4))


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

    def add_builds(self, repo: str, branch: str, images: List[Dict[List, str]]):
        if self.token is None:
            raise Exception("You need to login first")

        headers = {"Authorization": "JWT " + self.token}

        for image in images:
            for tag in image["tags"]:
                build = {"name": tag, "dockerfile_location": image["path"], "source_name": branch,
                         "source_type": "Branch",
                         "isNew": True}

                response = requests.post(self.API_URL + "/repositories/%s/autobuild/tags/" % repo, headers=headers,
                                         data=build)

                if response.status_code != 201:
                    raise Exception("ERROR [%d]: %s" % (response.status_code, response.text))


class Deployer:
    """Handles the Docker Hub deploy process."""

    def deploy(self, dist: str = "dist"):
        with open(os.path.join(dist, "images.json")) as image_list_file:
            image_list = json.load(image_list_file)

        if "DOCKERHUB_USERNAME" not in os.environ or not os.environ["DOCKERHUB_USERNAME"]:
            username = input("Enter Docker Hub username: ")
        else:
            username = os.environ["DOCKERHUB_USERNAME"]

        if "DOCKERHUB_PASSWORD" not in os.environ or not os.environ["DOCKERHUB_PASSWORD"]:
            password = getpass.getpass("Enter Docker Hub password: ")
        else:
            password = os.environ["DOCKERHUB_PASSWORD"]

        hub_updater = HubUpdater(username, password)

        try:
            hub_updater.login()
        except Exception as e:
            print(e, file=sys.stderr)
            sys.exit(1)

        hub_updater.clear_builds(image_list["repo"])
        hub_updater.add_builds(image_list["repo"], image_list["branch"], image_list["images"])
