# Intent API

Intent API is a specialized tool for managing network devices, serving as an abstraction layer for Custom GPTs. It leverages both Netmiko for SSH control and NetBox for network data management, facilitating vendor-agnostic, intent-based networking operations.

## Disclaimer

This tool is **not** intended for use in production environments, as it achieves a best-case correctness of 90.2 %, which is not sufficient for production use. We do not take responsibility for any damage resulting from the use of this tool. Please use the tool exclusively in testing and development environments.

## Features

- **Command Execution**: Send commands to network devices, ensuring compatibility and verification through subsequent `show` commands.
- **NetBox Integration**: Interact with NetBox to retrieve, create, update, and delete network-related data.
- **Authentication**: Basic HTTP authentication for accessing the API endpoints.

## Setup

### Prerequisites

Before running Intent API, ensure you have the following prerequisites installed and set up:

- [Python 3.12](https://www.python.org/)
- [uvicorn](https://www.uvicorn.org/)
- [ngrok](https://ngrok.com/download)
- [Docker](https://docs.docker.com/) and [Containerlab](https://containerlab.dev/install/) (for infrastructure setup)

### Installation

1. Clone the repository:

   ```bash
   git clone git@github.com:Stinktopf/intent-api.git
   cd intent-api
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

### Infrastructure Setup

1. Use Containerlab to deploy the network infrastructure:

   ```bash
   sudo containerlab deploy
   ```

2. SSH into the deployed devices to configure them:

   ```bash
   ssh <user>@<device_ip>
   ```

### Configuration

#### Setting up the `.env` File

The `.env` file is essential for configuring the environment variables that Intent API requires to operate. A template for this file is provided as `.env.template`. To create your own `.env` file:

1. Copy the template:

   ```bash
   cp .env.template .env
   ```

2. Open the `.env` file and fill in the necessary values.

#### Configuring the Custom GPT

The [GPT.md](./GPT.md) serves as a blueprint for replicating the functionality of our Custom GPT. It contains all the necessary parameters and settings to ensure that your Custom GPT behaves as intended when interacting with network devices and managing data through the Intent API.

#### Configuring the `router_config.yaml` File

The `router_config.yaml` file is crucial for managing device-specific credentials. By default, it contains credentials that apply to all devices of a certain type. However, you can override these credentials for specific devices by specifying the hostname and providing the necessary credentials.

Example `router_config.yaml` configuration:

```yaml
default:
  nokia_srl:
    username: "admin"
    password: "NokiaSrl1!"

overwrite:
  router1.example.com:
    username: "special_user1"
    password: "special_password1"
```

- **`default`**: Specifies the default username and password for all devices of the type `nokia_srl`.
- **`overwrite`**: Allows you to specify credentials for individual devices, identified by their hostname (e.g., `router1.example.com`). These credentials will take precedence over the default credentials.

Ensure that you update the `router_config.yaml` file with the correct access credentials for your network devices before running the API.

### Running the API

1. Start the API server:

   ```bash
   uvicorn main:app --port 8080
   ```

2. Access the API documentation at `https://<ngrok_domain>/docs`.