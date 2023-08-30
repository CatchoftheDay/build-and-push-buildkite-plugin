"""A Buildkite plugin to build and push container images to ECR"""
import os

from typing import List, Dict, Any

import yaml

BUILDKIT_VERSION: str = os.environ.get('BUILD_AND_PUSH_BUILDKIT_VERSION', 'v0.11.6')

ECR_ACCOUNT: str = "362995399210"
ECR_REPO_PREFIX: str = "catch"
ECR_REGION: str = "ap-southeast-2"
CURRENT_BRANCH: str = os.environ.get('BUILDKITE_BRANCH') if os.environ.get('BUILDKITE_BRANCH', '') != '' else 'no-branch'

PLUGIN_NAME: str = "build-and-push"
PLUGIN_ENV_PREFIX: str = f"BUILDKITE_PLUGIN_{PLUGIN_NAME.upper().replace('-', '_')}_"

BUILD_PLATFORMS: Dict[str, str] = {
    # platform => buildkite agent name
    'arm': 'aws/docker-arm',
    'x86': 'aws/docker',
}

BLOCK_ON_CONTAINER_SCAN = os.environ.get('BLOCK_BUILD_AND_PUSH_ON_SCAN', 'false').lower() == 'true'

def process_env_to_config() -> Dict[str, Any]:
    """Process buildkite plugin environment variables into a config dict"""
    config_definition: Dict[str, Any] = {
        'dockerfile_path': {
            'type': 'string',
            'default': 'Dockerfile',
        },
        'context_path': {
            'type': 'string',
            'default': '.',
        },
        'image_name': {
            'type': 'string',
            'default': os.environ['BUILDKITE_PIPELINE_NAME'],
        },
        'image_tag': {
            'type': 'string',
            'default': os.environ['BUILDKITE_COMMIT'][0:10],
        },
        'additional_tag': {
            'type': 'string',
            'default': None,
        },
        'build_args': {
            'type': 'list',
            'default': [],
        },
        'build_arm': {
            'type': 'bool',
            'default': True,
        },
        'build_x86': {
            'type': 'bool',
            'default': True,
        },
        'scan_image': {
            'type': 'bool',
            'default': True,
        },
        'group_key': {
            'type': 'string',
            'default': 'build-and-push',
        },
        'always_pull': {
            'type': 'bool',
            'default': True,
        },
        'composer_cache': {
            'type': 'bool',
            'default': False,
        },
        'npm_cache': {
            'type': 'bool',
            'default': False,
        },
    }

    config = {}

    def process_bool(value: str) -> bool:
        return value.lower() == 'true'

    def process_list(value: str) -> List[str]:
        return value.split(',')

    for name, value in os.environ.items():
        if name.startswith(PLUGIN_ENV_PREFIX):
            key = name.replace(PLUGIN_ENV_PREFIX, '').lower()

            if key not in config_definition:
                continue

            if config_definition[key]['type'] == 'bool':
                config[key] = process_bool(value)
            elif config_definition[key]['type'] == 'list':
                config[key] = process_list(value)
            else:
                config[key] = value

    for name, value in config_definition.items():
        if name not in config:
            config[name] = value.get('default', None)

    config['build_args'].append("GITHUB_TOKEN")

    config['group_key'] = sanitise_step_key(config['group_key'])

    config['fully_qualified_image_name'] = f'{ECR_ACCOUNT}.dkr.ecr.{ECR_REGION}.amazonaws.com/{ECR_REPO_PREFIX}/{config["image_name"]}'

    return config


def sanitise_step_key(key: str) -> str:
    """Step keys only accept alphanumeric characters, underscores, dashes and colons"""
    return ''.join([c for c in key if c.isalnum() or c in ['_', '-', ':']])


def create_build_step(platform: str, agent: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Create a step stub to build and push a container image for a given platform"""
    platform_image: str = f'{config["fully_qualified_image_name"]}:multi-platform-{config["image_tag"]}-{platform}'

    cache_from_tags: List[str] = sorted(set([
        config["image_tag"],
        CURRENT_BRANCH,
        'master',
        'main',
    ]))
    cache_from_images_stub: str = ''.join([f' --cache-from type=registry,ref={config["fully_qualified_image_name"]}:{tag}' for tag in cache_from_tags])

    build_args: str = ''
    if config['build_args']:
        build_args = '--build-arg ' + ' --build-arg '.join(config['build_args'])

    pull_stub: str = ''
    if config['always_pull']:
        pull_stub = '--pull'

    composer_cache_stub: str = ''
    if config['composer_cache']:
        composer_cache_stub = '--build-context composer-cache=.composer-cache'

    npm_cache_stub: str = ''
    if config['npm_cache']:
        npm_cache_stub = '--build-context npm-cache=.npm-cache'

    step = {
        'label': f':docker: Build and push {platform} image',
        'key': f'{config["group_key"]}-build-push-{platform}',
        'command': [
            f'docker buildx use builder || docker buildx create --bootstrap --name builder --use --driver docker-container --driver-opt image=moby/buildkit:{BUILDKIT_VERSION}',
            f'docker buildx build --push {pull_stub} --ssh default {cache_from_images_stub} {build_args} {composer_cache_stub} {npm_cache_stub} --tag {platform_image} -f {config["dockerfile_path"]} {config["context_path"]}',
        ],
        'agents': {
            'queue': agent,
        },
        'env': {
            'DOCKER_BUILDKIT': '1',
        },
        'plugins': [
            {
                'ecr#v2.7.0': {
                    'login': 'true',
                    'account_ids': ECR_ACCOUNT,
                    'region': ECR_REGION,
                },
            },
        ],
    }

    if config['composer_cache']:
        step['command'].insert(0, 'mkdir -p .composer-cache')
        step['command'].insert(0, 'echo ".composer-cache" >> .dockerignore')
        step['plugins'].append({
                'cache#v0.6.0': {
                    'backend': 's3',
                    'manifest': 'composer.lock',
                    'path': '.composer-cache',
                    'restore': 'file',
                    'save': 'pipeline'
                },
            }
        )

    if config['npm_cache']:
        step['command'].insert(0, 'mkdir -p .npm-cache')
        step['command'].insert(0, 'echo ".npm-cache" >> .dockerignore')
        step['plugins'].append({
                'cache#v0.6.0': {
                    'backend': 's3',
                    'manifest': 'package-lock.json',
                    'path': '.npm-cache',
                    'restore': 'file',
                    'save': 'pipeline'
                },
            }
        )

    return step


def create_oci_manifest_step(config: Dict[str, Any]) -> Dict[str, Any]:
    """Create a step stub to create a container manifest and push it to ECR"""
    images: List[str] = [f'{config["fully_qualified_image_name"]}:multi-platform-{config["image_tag"]}-{platform}' for platform, _ in BUILD_PLATFORMS.items()
                         if config[f'build_{platform}']]
    dependencies: List[str] = [
        f'{config["group_key"]}-build-push-{platform}' for platform, _ in BUILD_PLATFORMS.items() if config[f'build_{platform}']]

    step = {
        'label': ':docker: Create container manifest',
        'depends_on': dependencies,
        'key': f'{config["group_key"]}-manifest',
        'command': [
            f'docker buildx imagetools create -t {config["fully_qualified_image_name"]}:{config["image_tag"]} {" ".join(images)}',        ],
        'plugins': [
            {
                'ecr#v2.7.0': {
                    'login': 'true',
                    'account_ids': ECR_ACCOUNT,
                    'region': ECR_REGION,
                },
            }
        ],
    }

    if config['additional_tag']:
        step['command'].append(
            f'docker buildx imagetools create -t {config["fully_qualified_image_name"]}:{config["additional_tag"]} {" ".join(images)}')
        if CURRENT_BRANCH not in (config['additional_tag'], config['image_tag']):
            step['command'].append(
                f'docker buildx imagetools create -t {config["fully_qualified_image_name"]}:{CURRENT_BRANCH} {" ".join(images)}')
    elif config['image_tag'] != CURRENT_BRANCH:
        step['command'].append(
            f'docker buildx imagetools create -t {config["fully_qualified_image_name"]}:{CURRENT_BRANCH} {" ".join(images)}')

    return step


def create_scan_step(config: Dict[str, Any]) -> Dict[str, Any]:
    """Create a step stub to scan the container image with Rapid7"""
    step = {
        'label': ':docker: Scan container for security issues',
        'depends_on': f'{config["group_key"]}-manifest',
        'key': f'{config["group_key"]}-scan-container',
        'command': [
            f'docker pull {config["fully_qualified_image_name"]}:{config["image_tag"]}',
            'curl -o wizcli https://wizcli.app.wiz.io/latest/wizcli',
            'chmod +x ./wizcli',
            './wizcli auth --id $$WIZ_CLIENT_ID --secret $$WIZ_CLIENT_SECRET',
            f'./wizcli docker scan --image {config["fully_qualified_image_name"]}:{config["image_tag"]} -p "Container Scanning" -p "Secret Scanning" --tag pipeline={os.environ["BUILDKITE_PIPELINE_NAME"]} --tag pipeline_run={os.environ["BUILDKITE_BUILD_NUMBER"]}',
        ],
        'agents': {
            'queue': 'aws/docker',
        },
        'plugins': [
            {
                'ecr#v2.7.0': {
                    'login': 'true',
                    'account_ids': ECR_ACCOUNT,
                    'region': ECR_REGION,
                },
            }
        ],
    }

    return step


def main():
    """Generate and output to stdout a pipeline for building, pushing and scanning a multi-platform container image."""
    config = process_env_to_config()

    pipeline = {}
    pipeline['steps'] = []
    pipeline['steps'].append({
        'group': ':docker: Build and push images',
        'key': config['group_key'],
        'steps': [],
    })

    for platform, agent in BUILD_PLATFORMS.items():
        if config[f'build_{platform}']:
            pipeline['steps'][0]['steps'].append(
                create_build_step(platform, agent, config))

    pipeline['steps'][0]['steps'].append(create_oci_manifest_step(config))

    if config['scan_image']:
        if BLOCK_ON_CONTAINER_SCAN:
            pipeline['steps'][0]['steps'].append(create_scan_step(config))
        else:
            pipeline['steps'].append(create_scan_step(config))

    with open('pipeline.yaml', 'w', encoding="utf8") as file:
        yaml.dump(pipeline, file, width=1000)


if __name__ == '__main__':
    main()
