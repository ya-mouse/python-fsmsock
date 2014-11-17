from setuptools import setup, find_packages

dependency_links = []
install_requires = []

with open('requirements.txt') as f:
    for line in f:
        if line.startswith("#"):
            continue
        if '#egg=' in line:
            dependency_links.append(line)
            continue
        install_requires.append(line)

setup(
    name='python-fsmsock',
    version='0.2',
    description='Finite State Machine socket library for Python',
    author='Anton D. Kachalov',
    packages=find_packages(),
    platforms='any',
    zip_safe=False,
    include_package_data=True,
    dependency_links=dependency_links,
    install_requires=install_requires,
)