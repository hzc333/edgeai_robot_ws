from glob import glob

from setuptools import find_packages, setup

package_name = 'edgeai_system_tests'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md']),
        ('share/' + package_name + '/launch', glob('launch/*.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='hzc333',
    maintainer_email='huangzc333@gmail.com',
    description='EdgeAI system tests and mocks',
    license='Apache-2.0',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'mock_robot_agent = edgeai_system_tests.mocks.mock_robot_agent:main',
        ],
    },
)
