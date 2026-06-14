"""
Mock Home Assistant Server
Provides HA API endpoints for local testing without real Home Assistant.

Usage:
  - Run standalone: python test_mock_ha.py
  - Run in Docker: docker-compose -f docker-compose.test.yml up mock-ha
"""

from flask import Flask, jsonify, request
from datetime import datetime, timedelta
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Simulated entity states - can be modified via POST
ENTITY_STATES = {
    # Sensors
    'binary_sensor.rain': {'state': 'off', 'attributes': {}},
    'sensor.soil_moisture': {'state': '45', 'attributes': {'unit_of_measurement': '%'}},
    'sensor.temperature': {'state': '18', 'attributes': {'unit_of_measurement': '°C'}},
    'sensor.flow_meter': {'state': '0', 'attributes': {'unit_of_measurement': 'L/min'}},
    
    # Weather
    'weather.home': {
        'state': 'sunny',
        'attributes': {
            'temperature': 22,
            'precipitation_probability': 0,
            'forecast': [
                {'datetime': '2024-01-14T12:00:00', 'condition': 'sunny', 'temperature': 22},
                {'datetime': '2024-01-14T18:00:00', 'condition': 'sunny', 'temperature': 18},
            ]
        }
    },
    
    # Valves & switches
    'switch.irrigation_main': {'state': 'off', 'attributes': {}},
    'switch.pump': {'state': 'off', 'attributes': {}},
    'switch.zone1_valve': {'state': 'off', 'attributes': {}},
    'switch.zone2_valve': {'state': 'off', 'attributes': {}},
}

# History - simulates past state changes
ENTITY_HISTORY = {
    'binary_sensor.rain': [
        {'state': 'off', 'last_changed': '2024-01-14T06:00:00Z'},
        {'state': 'off', 'last_changed': '2024-01-14T12:00:00Z'},
    ],
    'weather.home': [
        {'state': 'sunny', 'last_changed': '2024-01-14T06:00:00Z'},
        {'state': 'cloudy', 'last_changed': '2024-01-14T10:00:00Z'},
        {'state': 'sunny', 'last_changed': '2024-01-14T14:00:00Z'},
    ],
}


@app.route('/api/states', methods=['GET'])
def get_all_states():
    """Get all entity states - HA API"""
    result = []
    for entity_id, state_obj in ENTITY_STATES.items():
        result.append({
            'entity_id': entity_id,
            **state_obj,
        })
    return jsonify(result)


@app.route('/api/states/<path:entity_id>', methods=['GET'])
def get_state(entity_id):
    """Get single entity state - HA API"""
    if entity_id in ENTITY_STATES:
        return jsonify({
            'entity_id': entity_id,
            **ENTITY_STATES[entity_id],
        })
    return jsonify({'error': 'Entity not found'}), 404


@app.route('/api/states/<path:entity_id>', methods=['POST'])
def set_state(entity_id):
    """Set entity state - HA API"""
    data = request.get_json() or {}
    if entity_id not in ENTITY_STATES:
        return jsonify({'error': 'Entity not found'}), 404
    
    ENTITY_STATES[entity_id]['state'] = data.get('state', 'unknown')
    ENTITY_STATES[entity_id]['attributes'] = data.get('attributes', {})
    logger.info(f"Set {entity_id} = {data.get('state')}")
    
    return jsonify({
        'entity_id': entity_id,
        **ENTITY_STATES[entity_id],
    })


@app.route('/api/history/period/<start_date>', methods=['GET'])
def get_history(start_date):
    """Get entity history - HA API
    
    Query params:
      - filter_entity_id: entity ID to get history for
      - end_time: end time (optional)
    """
    entity_id = request.args.get('filter_entity_id')
    
    if not entity_id:
        return jsonify([])
    
    if entity_id in ENTITY_HISTORY:
        return jsonify([ENTITY_HISTORY[entity_id]])
    
    return jsonify([[]])


@app.route('/api/services/homeassistant/call_service', methods=['POST'])
def call_service():
    """Call HA service - simplified"""
    data = request.get_json() or {}
    domain = data.get('domain', 'unknown')
    service = data.get('service', 'unknown')
    service_data = data.get('service_data', {})
    entity_id = service_data.get('entity_id')
    
    logger.info(f"Service call: {domain}/{service} on {entity_id}")
    
    if entity_id and entity_id in ENTITY_STATES:
        if service == 'turn_on':
            ENTITY_STATES[entity_id]['state'] = 'on'
        elif service == 'turn_off':
            ENTITY_STATES[entity_id]['state'] = 'off'
    
    return jsonify({'ok': True})


@app.route('/ws', methods=['GET'])
def websocket():
    """WebSocket endpoint stub"""
    return 'Upgrade Required', 101


# Test helper endpoints
@app.route('/test/set-rain', methods=['POST'])
def test_set_rain():
    """Helper: simulate rain"""
    data = request.get_json() or {}
    state = data.get('state', 'on')  # on/off
    ENTITY_STATES['binary_sensor.rain']['state'] = state
    ENTITY_HISTORY['binary_sensor.rain'].append({
        'state': state,
        'last_changed': datetime.utcnow().isoformat() + 'Z'
    })
    logger.info(f"[TEST] Set rain = {state}")
    return jsonify({'ok': True})


@app.route('/test/set-weather', methods=['POST'])
def test_set_weather():
    """Helper: set weather condition"""
    data = request.get_json() or {}
    condition = data.get('condition', 'sunny')  # sunny/rainy/cloudy
    ENTITY_STATES['weather.home']['state'] = condition
    ENTITY_HISTORY['weather.home'].append({
        'state': condition,
        'last_changed': datetime.utcnow().isoformat() + 'Z'
    })
    logger.info(f"[TEST] Set weather = {condition}")
    return jsonify({'ok': True})


@app.route('/test/set-soil-moisture', methods=['POST'])
def test_set_soil():
    """Helper: set soil moisture %"""
    data = request.get_json() or {}
    moisture = data.get('moisture', '50')
    ENTITY_STATES['sensor.soil_moisture']['state'] = str(moisture)
    logger.info(f"[TEST] Set soil moisture = {moisture}%")
    return jsonify({'ok': True})


@app.route('/test/reset-history', methods=['POST'])
def test_reset():
    """Helper: reset all history"""
    ENTITY_HISTORY.clear()
    for entity_id in ENTITY_STATES:
        ENTITY_HISTORY[entity_id] = []
    logger.info("[TEST] History reset")
    return jsonify({'ok': True})


@app.route('/health', methods=['GET'])
def health():
    """Health check"""
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    logger.info("Mock Home Assistant Server starting on http://0.0.0.0:5050")
    logger.info("Available endpoints:")
    logger.info("  - GET /api/states - list all entities")
    logger.info("  - GET /api/states/<entity_id> - get entity")
    logger.info("  - POST /api/states/<entity_id> - set entity")
    logger.info("  - GET /api/history/period/<date> - get history")
    logger.info("  - POST /test/* - test helpers")
    logger.info("")
    logger.info("Test helpers:")
    logger.info("  - POST /test/set-rain {state: 'on'|'off'}")
    logger.info("  - POST /test/set-weather {condition: 'sunny'|'rainy'|'cloudy'}")
    logger.info("  - POST /test/set-soil-moisture {moisture: 45}")
    logger.info("  - POST /test/reset-history")
    
    app.run(host='0.0.0.0', port=5050, debug=True)
