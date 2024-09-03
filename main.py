import json
import logging
import os
from typing import List, Any

import yaml
import ngrok
import pynetbox
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.openapi.utils import get_openapi
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from netmiko import (
    ConnectHandler,
    NetMikoTimeoutException,
    NetMikoAuthenticationException,
)
from pydantic import BaseModel, Field, validator

# Load environment variables from .env file
load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="Netrunner API",
    description="API for managing network devices and interacting with NetBox",
    version="1.0.0",
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration variables
ngrok_auth_token = os.getenv("NGROK_AUTH_TOKEN")
ngrok_domain = os.getenv("NGROK_DOMAIN")
netbox_url = os.getenv("NETBOX_URL")
netbox_token = os.getenv("NETBOX_TOKEN")
admin_user = os.getenv("ADMIN_USER")
admin_password = os.getenv("ADMIN_PASSWORD")

# Initialize ngrok
ngrok.set_auth_token(ngrok_auth_token)
ngrok.forward(
    addr="localhost:8080",
    domain=ngrok_domain,
    authtoken=ngrok_auth_token,
    bind_tls=True,
)
logger.info(f"ngrok tunnel created at {ngrok_domain}")

# Initialize NetBox API client
netbox = pynetbox.api(url=netbox_url, token=netbox_token)

# HTTP Basic Authentication
security = HTTPBasic()
users = {
    admin_user: admin_password,
}


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    """Verify user credentials for HTTP Basic Authentication."""
    if (
        credentials.username not in users
        or users[credentials.username] != credentials.password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def load_router_config(yaml_path: str) -> dict:
    with open(yaml_path, "r") as file:
        config = yaml.safe_load(file)
    return config


def get_router_credentials(config: dict, device_type: str, host: str) -> dict:
    credentials = config.get("default", {}).get(device_type, {})
    host_credentials = config.get("overwrite", {}).get(host, {})
    credentials.update(host_credentials)
    return credentials


yaml_path = os.getenv("ROUTER_CONFIG_YAML", "router_config.yaml")
router_config = load_router_config(yaml_path)


class CommandSequenceInfo(BaseModel):
    device_type: str = Field(..., description="Type of the network device")
    host: str = Field(..., description="Hostname or IP address of the device")
    commands: List[str] = Field(
        ..., description="List of commands to execute on the device"
    )
    i_conducted_a_online_search_before_this_request: bool = Field(..., description="Indicates if an online search was performed before sending commands")

    @validator("device_type")
    def validate_device_type(cls, v):
        valid_device_types = ["cisco_ios", "nokia_srl", "juniper"]
        if v not in valid_device_types:
            raise ValueError("Invalid device type")
        return v


class ItemData(BaseModel):
    data: str = Field(..., description="Item data as a JSON string")

    @validator("data")
    def validate_data(cls, data):
        try:
            json_data = json.loads(data)
        except json.JSONDecodeError:
            raise ValueError("Item data must be a valid JSON string")
        return json_data


def get_netbox_model(category: str, model: str):
    """
    Retrieve a NetBox model for the given category and model name.
    """
    try:
        category_attr = getattr(netbox, category, None)
        if category_attr is None:
            raise HTTPException(
                status_code=404, detail=f"Category '{category}' not found"
            )

        model_attr = getattr(category_attr, model, None)
        if model_attr is None:
            raise HTTPException(
                status_code=404,
                detail=f"Model '{model}' in category '{category}' not found",
            )

        return model_attr
    except AttributeError as e:
        raise HTTPException(
            status_code=404, detail=f"Error accessing {category}/{model}: {str(e)}"
        )


def serialize_object(obj: Any):
    """Serialize a NetBox object."""
    return obj.serialize() if obj else None


@app.post(
    "/send_commands",
    summary="Send commands to a device",
    response_description="Output of the commands executed",
)
async def send_commands(
    command_sequence_info: CommandSequenceInfo,
    username: str = Depends(verify_credentials),
):
    """
    Send a sequence of commands to a specified network device and return the output.
    """
    if not command_sequence_info.i_conducted_a_online_search_before_this_request:
        raise HTTPException(
            status_code=400,
            detail="Online documentation must be consulted before sending commands. Set 'i_conducted_a_online_search_before_this_request' to True after consulting and reset it to False after completion of one intent or when encountering errors. After online search you can try again.",
        )

    try:
        credentials = get_router_credentials(
            router_config, command_sequence_info.device_type, command_sequence_info.host
        )

        if not credentials:
            raise HTTPException(
                status_code=404,
                detail="Credentials not found for the specified device type or host",
            )

        device = {
            "device_type": command_sequence_info.device_type,
            "host": command_sequence_info.host,
            "username": credentials.get("username"),
            "password": credentials.get("password"),
            "port": 22,
        }
        connection = ConnectHandler(**device)
        output = {}
        for command in command_sequence_info.commands:
            command_output = connection.send_command(command)
            output[command] = command_output
        connection.disconnect()
        return {"output": output}
    except NetMikoTimeoutException as e:
        logger.error(f"Connection timeout error: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Connection timeout error", "details": str(e)},
        )
    except NetMikoAuthenticationException as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=401, detail={"error": "Authentication error", "details": str(e)}
        )
    except Exception as e:
        logger.error(f"Error sending commands: {e}")
        raise HTTPException(
            status_code=500, detail={"error": "General error", "details": str(e)}
        )


@app.post(
    "/netbox/get_items",
    summary="Get NetBox items",
    response_description="List of items from the specified NetBox model",
)
async def get_items(
    category: str, model: str, username: str = Depends(verify_credentials)
):
    """
    Retrieve all items from a specified NetBox model.
    """
    try:
        nb_model = get_netbox_model(category, model)
        items = nb_model.all()
        return [serialize_object(item) for item in items]
    except Exception as e:
        logger.error(f"Error getting items: {e}")
        raise HTTPException(
            status_code=500, detail={"error": "Error getting items", "details": str(e)}
        )


@app.post(
    "/netbox/get_item_by_id",
    summary="Get a NetBox item by ID",
    response_description="Serialized item from NetBox",
)
async def get_item_by_id(
    category: str, model: str, id: int, username: str = Depends(verify_credentials)
):
    """
    Retrieve a specific item from NetBox by its ID.
    """
    try:
        nb_model = get_netbox_model(category, model)
        item = nb_model.get(id)
        if not item:
            raise HTTPException(
                status_code=404, detail=f"{model.capitalize()} not found"
            )
        return serialize_object(item)
    except Exception as e:
        logger.error(f"Error getting item by ID: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Error getting item by ID", "details": str(e)},
        )


@app.post(
    "/netbox/{category}/{model}",
    summary="Create a NetBox item",
    response_description="Serialized created item from NetBox",
)
async def create_item(
    category: str,
    model: str,
    item_data: ItemData,
    username: str = Depends(verify_credentials),
):
    """
    Create a new item in a specified NetBox model.
    """
    try:
        nb_model = get_netbox_model(category, model)
        new_item = nb_model.create(**dict(item_data.data))
        if not new_item:
            raise HTTPException(status_code=400, detail=f"Failed to create {model}")
        return serialize_object(new_item)
    except Exception as e:
        logger.error(f"Error creating item: {e}")
        raise HTTPException(
            status_code=500, detail={"error": "Error creating item", "details": str(e)}
        )


@app.patch(
    "/netbox/{category}/{model}/{id}",
    summary="Partially update a NetBox item",
    response_description="Serialized partially updated item from NetBox",
)
async def patch_item(
    category: str,
    model: str,
    id: int,
    item_data: ItemData,
    username: str = Depends(verify_credentials),
):
    """
    Partially update an existing item in a specified NetBox model.
    """
    try:
        nb_model = get_netbox_model(category, model)
        item = nb_model.get(id)
        if not item:
            raise HTTPException(
                status_code=404, detail=f"{model.capitalize()} not found"
            )
        item.update(dict(item_data.data))
        return serialize_object(item)
    except Exception as e:
        logger.error(f"Error partially updating item: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Error partially updating item", "details": str(e)},
        )


@app.delete(
    "/netbox/{category}/{model}/{id}",
    summary="Delete a NetBox item",
    response_description="Success message upon deletion",
)
async def delete_item(
    category: str, model: str, id: int, username: str = Depends(verify_credentials)
):
    """
    Delete an existing item in a specified NetBox model.
    """
    try:
        nb_model = get_netbox_model(category, model)
        item = nb_model.get(id)
        if not item:
            raise HTTPException(
                status_code=404, detail=f"{model.capitalize()} not found"
            )
        item.delete()
        return {"detail": f"{model.capitalize()} deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting item: {e}")
        raise HTTPException(
            status_code=500, detail={"error": "Error deleting item", "details": str(e)}
        )


@app.get(
    "/openapi",
    summary="Get Custom OpenAPI Specification",
    response_description="Custom OpenAPI specification for the API",
)
async def get_custom_openapi_spec():
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    openapi_schema["servers"] = [{"url": f"https://{ngrok_domain}"}]

    # Update the request body for the /send_commands path
    if "/send_commands" in openapi_schema["paths"]:
        openapi_schema["paths"]["/send_commands"]["post"]["requestBody"] = {
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/CommandSequenceInfo"}
                }
            },
            "required": True,
        }

    # Update request bodies for the NetBox related paths
    netbox_paths = ["/netbox/{category}/{model}"]
    for path in netbox_paths:
        if path in openapi_schema["paths"]:
            if "post" in openapi_schema["paths"][path]:
                openapi_schema["paths"][path]["post"]["requestBody"] = {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ItemData"}
                        }
                    },
                }

    return openapi_schema

