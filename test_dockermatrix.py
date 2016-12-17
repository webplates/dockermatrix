import unittest

from dockermatrix import *
import semver


class ImageTest(unittest.TestCase):
    def setUp(self):
        self.image = Image({'1', '1.0', '1.0.0'}, 'images/1.0')

    def test_has_tags(self):
        self.assertSetEqual({'1', '1.0', '1.0.0'}, self.image.tags)

    def test_has_path(self):
        self.assertEqual('images/1.0', self.image.path)


class ImageBuildTest(unittest.TestCase):
    def setUp(self):
        self.build = ImageBuild(semver.VersionInfo(1, 0, 0, None, None), ('option', None, 'other_option'))

    def test_has_version(self):
        self.assertTupleEqual(semver.VersionInfo(1, 0, 0, None, None), self.build.version)

    def test_has_options(self):
        self.assertTupleEqual(('option', None, 'other_option'), self.build.options)

    def test_returns_formatted_version(self):
        self.assertEqual('1.0.0', self.build.get_formatted_version())

    def test_filters_options(self):
        self.assertListEqual(['option', 'other_option'], self.build.filter_options())


class BuildMatrixTest(unittest.TestCase):
    def setUp(self):
        builds = {
            ImageBuild(semver.VersionInfo(1, 0, 0, None, None), ('option',)),
            ImageBuild(semver.VersionInfo(1, 0, 0, None, None), (None,)),
        }

        self.matrix = BuildMatrix(builds)

    def test_has_the_latest_versions(self):
        self.assertDictEqual(
            {'1.0.0': {'1', '1.0'}},
            self.matrix.latest
        )

    def test_detects_the_latest_versions(self):
        builds = {
            ImageBuild(semver.VersionInfo(1, 0, 0, None, None), ()),
            ImageBuild(semver.VersionInfo(1, 0, 1, None, None), ()),
            ImageBuild(semver.VersionInfo(1, 1, 0, None, None), ()),
            ImageBuild(semver.VersionInfo(2, 0, 0, None, None), ()),
        }

        self.matrix = BuildMatrix(builds)

        self.assertDictEqual(
            {'1.0.1': {'1.0'}, '1.1.0': {'1', '1.1'}, '2.0.0': {'2', '2.0'}},
            self.matrix.latest
        )

    def test_builds_matrix(self):
        images = list(self.matrix.build('dist'))

        self.assertIsInstance(images[0][0], ImageBuild)
        self.assertIsInstance(images[0][1], Image)

        self.assertIsInstance(images[1][0], ImageBuild)
        self.assertIsInstance(images[1][1], Image)
