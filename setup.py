from Cython.Build import cythonize
from Cython.Distutils import build_ext
from setuptools import setup, find_packages
from distutils.core import Extension

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

exts = [
    Extension('async', sources=['fsmsock/async.pyx']),
    Extension('proto/base', sources=['fsmsock/proto/base.pyx']),
    Extension('proto/realcom', sources=['fsmsock/proto/realcom.pyx']),
]

setup(
    name='python-fsmsock',
    version='0.2',
    description='Finite State Machine socket library for Python',
    author='Anton D. Kachalov',
    ext_package='fsmsock',
    ext_modules=cythonize(exts),
    platforms='any',
    zip_safe=False,
    include_package_data=True,
    dependency_links=dependency_links,
    install_requires=install_requires,
)