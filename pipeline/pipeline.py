"""A Buildkite plugin to build and push container images to ECR"""
import os

from typing import List, Dict, Any

import yaml

ECR_ACCOUNT: str = "362995399210"
ECR_REPO_PREFIX: str = "catch"
ECR_REGION: str = "ap-southeast-2"

PLUGIN_NAME: str = "build-and-push"
PLUGIN_ENV_PREFIX: str = f"BUILDKITE_PLUGIN_{PLUGIN_NAME.upper()}_"

BUILD_PLATFORMS: Dict[str, str] = {
    # platform => buildkite agent name
    'arm': 'aws/docker-arm',
    'x86': 'aws/docker',
}

def process_env_to_config() -> Dict[str, Any]:
    """Process buildkite plugin environment variables into a config dict"""
    config_definition: Dict[str, Any] = {
        'dockerfile': {
            'type': 'string',
            'default': 'Dockerfile',
        },
        'dockerfile_path': {
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
        'scan_images': {
            'type': 'bool',
            'default': True,
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

    return config


def create_build_step(platform: str, agent: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Create a step stub to build and push a container image for a given platform"""
    image: str = f'{ECR_ACCOUNT}.dkr.ecr.{ECR_REGION}.amazonaws.com/{ECR_REPO_PREFIX}/{config["image_name"]}:{config["image_tag"]}-{platform}'

    build_args = ''
    if config['build_args']:
        build_args = '--build-arg ' + ' --build-arg '.join(config['build_args'])

    step = {
        'label': f':docker: Build and push {platform} image',
        'key': f'build-push-{platform}',
        'command': [
            f'docker buildx build --push --ssh default {build_args} --tag {image} -f {config["dockerfile"]} {config["dockerfile_path"]}',
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

    return step


def create_oci_manifest_step(config: Dict[str, Any]) -> Dict[str, Any]:
    """Create a step stub to create a container manifest and push it to ECR
    
        We also delete the individual platform images as they are no longer needed.
    """
    images: List[str] = [f'{ECR_ACCOUNT}.dkr.ecr.{ECR_REGION}.amazonaws.com/{ECR_REPO_PREFIX}/{config["image_name"]}:{config["image_tag"]}-{platform}' for platform, _ in BUILD_PLATFORMS.items()
                         if config[f'build_{platform}']]
    dependencies: List[str] = [
        f'build-push-{platform}' for platform, _ in BUILD_PLATFORMS.items() if config[f'build_{platform}']]

    step = {
        'label': ':docker: Create container manifest',
        'depends_on': dependencies,
        'key': 'create-container-manifest',
        'command': [
            f'docker manifest create {ECR_ACCOUNT}.dkr.ecr.{ECR_REGION}.amazonaws.com/{ECR_REPO_PREFIX}/{config["image_name"]}:{config["image_tag"]} {" ".join(images)}',
            f'docker manifest push {ECR_ACCOUNT}.dkr.ecr.{ECR_REGION}.amazonaws.com/{ECR_REPO_PREFIX}/{config["image_name"]}:{config["image_tag"]}',
        ],
    }

    step['command'].extend(
        [f'aws ecr batch-delete-image --registry-id {ECR_ACCOUNT} --repository-name {ECR_REPO_PREFIX}/{config["image_name"]} --image-ids TAG="{config["image_tag"]}-{platform}"' for platform, _ in BUILD_PLATFORMS.items() if config[f'build_{platform}']])

    return step


def create_scan_step(config: Dict[str, Any]) -> Dict[str, Any]:
    """Create a step stub to scan the container image with Rapid7"""
    image: str = f'{ECR_ACCOUNT}.dkr.ecr.{ECR_REGION}.amazonaws.com/{ECR_REPO_PREFIX}/{config["image_name"]}:{config["image_tag"]}'

    step = {
        'label': ':docker: Scan container with Rapid7',
        'depends_on': "create-container-manifest",
        'key': 'scan-container',
        'command': [
            'if [[ -z "$${RAPID7_API_KEY}" ]]; then echo "A Rapid7 API key needs to be added to your build secrets as RAPID7_API_KEY"; exit 1; fi',
            f'docker save {image} -o "{config["image_name"]}.tar"',
            f'docker run --rm -v $(pwd)/docker_image.tar:/docker_image.tar rapid7/container-image-scanner:latest -f=/docker_image.tar -k=$$RAPID7_API_KEY -r=au --buildId "{config["image_tag"]}" --buildName {config["image_name"]}',
        ],
        'agents': {
            'queue': 'docker',
        },
    }

    return step


def main():
    """Generate and output to stdout a pipeline for building, pushing and scanning a multi-platform container image."""
    config = process_env_to_config()

    pipeline = {}
    pipeline['steps'] = []
    pipeline['steps'].append({
        'group': ':docker: Build and push images',
        'key': 'build-and-push',
        'steps': [],
    })

    for platform, agent in BUILD_PLATFORMS.items():
        if config[f'build_{platform}']:
            pipeline['steps'][0]['steps'].append(
                create_build_step(platform, agent, config))

    pipeline['steps'][0]['steps'].append(create_oci_manifest_step(config))

    pipeline['steps'].append(create_scan_step(config))

    with open('pipeline.yaml', 'w', encoding="utf8") as file:
        yaml.dump(pipeline, file, width=1000)


if __name__ == '__main__':
    main()
