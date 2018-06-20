import glob
import setuptools

with open("README.md", "r") as readmeFile:
    longDescription = readmeFile.read()

with open("VERSION", "r") as versionFile:
    version = versionFile.read().strip()

setuptools.setup(
    name="pychado",
    version=version,
    author="Christoph Puethe",
    author_email="path-help@sanger.ac.uk",
    description="Tools to access CHADO databases",
    long_description=longDescription,
    long_description_content_type="text/markdown",
    url="https://github.com/puethe/chado-tools/",
    packages = setuptools.find_packages(),
    scripts=['scripts/chado-tools'],
    test_suite="nose.collector",
    tests_require=["nose >= 1.3"],
    license="GPLv3",
    classifiers=[
        "Programming Language :: Python :: 3 :: Only",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering :: Bio-Informatics",
        "Development Status :: 1 - Planning",
    ],
)