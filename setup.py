""" setup.py """

from setuptools import setup, find_packages

from awlogin.version import __version__

with open('requirements.txt') as f:
    REQUIREMENTS = f.read().splitlines()

setup(
    name='awlogin',
    version=__version__,
    description='AWS Secure CLI MFA Logon Utility',
    long_description=open('README.md').read(),
    author='Sven Kobow',
    author_email='sk@skobow.net',
    url='https://github.com/skobow/awlogin',
    packages=find_packages(exclude=['tests*']),
    package_dir={'awlogin': 'awlogin'},
    license="MIT",
    py_modules=['awlogin'],
    install_requires=REQUIREMENTS,
    entry_points = {
        'console_scripts': [
            'awlogin = awlogin.awlogin:main'
        ],
    }
)
