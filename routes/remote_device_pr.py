import base64

from flask import Blueprint, jsonify, request, current_app, Response
import os
import yaml
from pyplayready.device import Device as PlayReadyDevice
from pyplayready.cdm import Cdm as PlayReadyCDM
from pyplayready import PSSH as PlayReadyPSSH
from pyplayready.misc.exceptions import (InvalidSession, TooManySessions, InvalidLicense, InvalidPssh)
from custom_functions.database.user_db import fetch_username_by_api_key
from custom_functions.decrypt.api_decrypt import is_base64
from custom_functions.user_checks.device_allowed import user_allowed_to_use_device
from pathlib import Path




remotecdm_pr_bp = Blueprint('remotecdm_pr', __name__)
with open(f'{os.getcwd()}/configs/config.yaml', 'r') as file:
    config = yaml.safe_load(file)

@remotecdm_pr_bp.route('/remotecdm/playready', methods=['GET', 'HEAD'])
def remote_cdm_playready():
    if request.method == 'GET':
        return jsonify({
            'message': 'OK'
        })
    if request.method == 'HEAD':
        response = Response(status=200)
        response.headers['Server'] = 'playready serve'
        return response


@remotecdm_pr_bp.route('/remotecdm/playready/deviceinfo', methods=['GET'])
def remote_cdm_playready_deviceinfo():
    base_name = config["default_pr_cdm"]
    if not base_name.endswith(".prd"):
        full_file_name = (base_name + ".prd")
    device = PlayReadyDevice.load(f'{os.getcwd()}/configs/CDMs/PR/{full_file_name}')
    cdm = PlayReadyCDM.from_device(device)
    return jsonify({
        'security_level': cdm.security_level,
        'host': f'{config["fqdn"]}/remotecdm/playready',
        'secret': f'{config["remote_cdm_secret"]}',
        'device_name': Path(base_name).stem
    })

@remotecdm_pr_bp.route('/remotecdm/playready/deviceinfo/<device>', methods=['GET'])
def remote_cdm_playready_deviceinfo_specific(device):
    if request.method == 'GET':
        base_name = Path(device).with_suffix('.prd').name
        api_key = request.headers['X-Secret-Key']
        username = fetch_username_by_api_key(api_key)
        device = PlayReadyDevice.load(f'{os.getcwd()}/configs/CDMs/{username}/PR/{base_name}')
        cdm = PlayReadyCDM.from_device(device)
        return jsonify({
            'security_level': cdm.security_level,
            'host': f'{config["fqdn"]}/remotecdm/widevine',
            'secret': f'{api_key}',
            'device_name': Path(base_name).stem
        })

@remotecdm_pr_bp.route('/remotecdm/playready/<device>/open', methods=['GET'])
def remote_cdm_playready_open(device):
    if str(device).lower() == config['default_pr_cdm'].lower():
        pr_device = PlayReadyDevice.load(f'{os.getcwd()}/configs/CDMs/PR/{config["default_pr_cdm"]}.prd')
        cdm = current_app.config['CDM'] = PlayReadyCDM.from_device(pr_device)
        session_id = cdm.open()
        return jsonify({
            'message': 'Success',
            'data': {
                'session_id': session_id.hex(),
                'device': {
                    'security_level': cdm.security_level
                }
            }
        })
    if request.headers['X-Secret-Key'] and str(device).lower() != config['default_pr_cdm'].lower():
        api_key = request.headers['X-Secret-Key']
        user = fetch_username_by_api_key(api_key=api_key)
        if user:
            if user_allowed_to_use_device(device=device, username=user):
                pr_device = PlayReadyDevice.load(f'{os.getcwd()}/configs/CDMs/{user}/PR/{device}.prd')
                cdm = current_app.config['CDM'] = PlayReadyCDM.from_device(pr_device)
                session_id = cdm.open()
                return jsonify({
                    'message': 'Success',
                    'data': {
                        'session_id': session_id.hex(),
                        'device': {
                            'security_level': cdm.security_level
                        }
                    }
                })
            else:
                return jsonify({
                    'message': f"Device '{device}' is not found or you are not authorized to use it.",
                }), 403
        else:
            return jsonify({
                'message': f"Device '{device}' is not found or you are not authorized to use it.",
            }), 403
    else:
        return jsonify({
            'message': f"Device '{device}' is not found or you are not authorized to use it.",
        }), 403

@remotecdm_pr_bp.route('/remotecdm/playready/<device>/close/<session_id>', methods=['GET'])
def remote_cdm_playready_close(device, session_id):
    try:
        session_id = bytes.fromhex(session_id)
        cdm = current_app.config["CDM"]
        if not cdm:
            return jsonify({
                'message': f'No CDM for "{device}" has been opened yet. No session to close'
            }), 400
        try:
            cdm.close(session_id)
        except InvalidSession:
            return jsonify({
                'message': f'Invalid session ID "{session_id.hex()}", it may have expired'
            }), 400
        return jsonify({
            'message': f'Successfully closed Session "{session_id.hex()}".',
        }), 200
    except Exception as e:
        return jsonify({
            'message': f'Failed to close Session "{session_id.hex()}".'
        }), 400

@remotecdm_pr_bp.route('/remotecdm/playready/<device>/get_license_challenge', methods=['POST'])
def remote_cdm_playready_get_license_challenge(device):
    body = request.get_json()
    for required_field in ("session_id", "init_data"):
        if not body.get(required_field):
            return jsonify({
                'message': f'Missing required field "{required_field}" in JSON body'
            }), 400
    cdm = current_app.config["CDM"]
    session_id = bytes.fromhex(body["session_id"])
    init_data = body["init_data"]
    if not init_data.startswith("<WRMHEADER"):
        try:
            pssh = PlayReadyPSSH(init_data)
            if pssh.wrm_headers:
                init_data = pssh.wrm_headers[0]
        except InvalidPssh as e:
            return jsonify({
                'message': f'Unable to parse base64 PSSH, {e}'
            })
    try:
        license_request = cdm.get_license_challenge(
            session_id=session_id,
            wrm_header=init_data
        )
    except InvalidSession:
        return jsonify({
            'message': f"Invalid Session ID '{session_id.hex()}', it may have expired."
        })
    except Exception as e:
        return jsonify({
            'message': f'Error, {e}'
        })
    return jsonify({
        'message': 'success',
        'data': {
            'challenge': license_request
        }
    })

@remotecdm_pr_bp.route('/remotecdm/playready/<device>/parse_license', methods=['POST'])
def remote_cdm_playready_parse_license(device):
    body = request.get_json()
    for required_field in ("license_message", "session_id"):
        if not body.get(required_field):
            return jsonify({
                'message': f'Missing required field "{required_field}" in JSON body'
            })
    cdm = current_app.config["CDM"]
    if not cdm:
        return jsonify({
            'message': f"No Cdm session for {device} has been opened yet. No session to use."
        })
    session_id = bytes.fromhex(body["session_id"])
    license_message = body["license_message"]
    if is_base64(license_message):
        license_message = base64.b64decode(license_message).decode("utf-8")
    try:
        cdm.parse_license(session_id, license_message)
    except InvalidSession:
        return jsonify({
            'message': f"Invalid Session ID '{session_id.hex()}', it may have expired."
        })
    except InvalidLicense as e:
        return jsonify({
            'message': f"Invalid License, {e}"
        })
    except Exception as e:
        return jsonify({
            'message': f"Error, {e}"
        })
    return jsonify({
        'message': 'Successfully parsed and loaded the Keys from the License message'
    })

@remotecdm_pr_bp.route('/remotecdm/playready/<device>/get_keys', methods=['POST'])
def remote_cdm_playready_get_keys(device):
    body = request.get_json()
    for required_field in ("session_id",):
        if not body.get(required_field):
            return jsonify({
                'message': f'Missing required field "{required_field}" in JSON body'
            })
    session_id = bytes.fromhex(body["session_id"])
    cdm = current_app.config["CDM"]
    if not cdm:
        return jsonify({
            'message': f"Missing required field '{required_field}' in JSON body."
        })
    try:
        keys = cdm.get_keys(session_id)
    except InvalidSession:
        return jsonify({
            'message': f"Invalid Session ID '{session_id.hex()}', it may have expired."
        })
    except Exception as e:
        return jsonify({
            'message': f"Error, {e}"
        })
    keys_json = [
        {
            "key_id": key.key_id.hex,
            "key": key.key.hex(),
            "type": key.key_type.value,
            "cipher_type": key.cipher_type.value,
            "key_length": key.key_length,
        }
        for key in keys
    ]
    return jsonify({
        'message': 'success',
        'data': {
            'keys': keys_json
        }
    })
