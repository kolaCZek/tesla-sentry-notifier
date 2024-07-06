from datetime import datetime
import json
import logging
import os
import paho.mqtt.client as mqtt
import pytz
import requests
import signal
import teslapy
import time

log_format = os.environ.get('LOG_FORMAT', '%(asctime)s %(levelname)s: %(message)s')
log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
timezone_str = os.environ.get('TZ', 'UTC')

tesla_user = os.environ.get('TESLA_USER')
cars_vin_filter = os.environ.get('CARS_VIN', '').upper()

timer = int(os.environ.get('TIMER', 10))
timer_skip = int(os.environ.get('TIMER_SKIP', 120))

mqtt_enabled =  os.environ.get('MQTT_ENABLED', 'False').lower() in ('true', '1', 't')
mqtt_server = os.environ.get('MQTT_SERVER')
mqtt_port = int(os.environ.get('MQTT_PORT', 1883))
mqtt_user = os.environ.get('MQTT_USER')
mqtt_pass = os.environ.get('MQTT_PASS')
mqtt_topic_prefix = os.environ.get('MQTT_TOPIC', 'tesla-sentry')

ntfy_enabled = os.environ.get('NTFY_ENABLED', 'False').lower() in ('true', '1', 't')
ntfy_server = os.environ.get('NTFY_SERVER', 'https://ntfy.sh')
ntfy_topic = os.environ.get('NTFY_TOPIC')
ntfy_token = os.environ.get('NTFY_TOKEN')

logging.basicConfig(format=log_format)
logging.getLogger().setLevel(level=log_level)

if not os.path.isfile('/etc/tesla-sentry-notifier/cache.json'):
    logging.info('Cache file not found - creating new')
    with open('/etc/tesla-sentry-notifier/cache.json', 'w') as file:
        json.dump({}, file)

tesla = teslapy.Tesla(email=tesla_user, cache_file='/etc/tesla-sentry-notifier/cache.json')
mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

def current_time():
    timezone = pytz.timezone(timezone_str)
    current_time = datetime.now(timezone)
    return str(current_time)

def get_vehicles():
    logging.debug('Getting vehicle list')
    vehicles = tesla.vehicle_list()

    logging.info('Get %s vehicles from Tesla API', len(vehicles))

    if cars_vin_filter:
        vehicles = [vehicle for vehicle in vehicles if 'vin' in vehicle and vehicle['vin'] in cars_vin_filter]
        logging.info('Returning %i vehicles after VIN filter applied', len(vehicles))

    for vehicle in vehicles:
        logging.debug('%s - %s', vehicle['vin'], vehicle['display_name'])

    return vehicles

def is_sentry_enabled(vehicle_state):
    if 'sentry_mode' in vehicle_state and vehicle_state['sentry_mode'] == True:
        return True

    return False

def is_sentry_triggered(vehicle_state):
    if 'center_display_state' in vehicle_state and vehicle_state['center_display_state'] == 7:
        return True

    return False

def update_mqtt(vehicle):
    if not mqttc.is_connected():
        return False

    mqtt_topic = '{prefix}/{vin}/'.format(prefix=mqtt_topic_prefix, vin=vehicle['vin'])
    logging.debug('MQTT: Updating topic %s', mqtt_topic)

    mqttc.publish(mqtt_topic + 'vehicle_online', vehicle['vehicle_online'])
    mqttc.publish(mqtt_topic + 'sentry_enabled', vehicle['sentry_enabled'])
    mqttc.publish(mqtt_topic + 'sentry_triggered', vehicle['sentry_triggered'])
    mqttc.publish(mqtt_topic + 'last_update', current_time())

def ntfy_send_message(vehicle):
    if not ntfy_server or not ntfy_topic:
        logging.error('NTFY: Server or Topic not set!')
        return False

    ntfy_url = '{server}/{topic}'.format(server=ntfy_server, topic=ntfy_topic)

    ntfy_message = 'Sentry Mode Triggered!'
    ntfy_headers = {
        'Title': vehicle['display_name'],
        'Priority': 'high',
        'Tags': 'warning'
    }

    if ntfy_token:
        logging.debug('NTFY: Sending message with auth token')
        ntfy_headers['Authorization'] = 'Bearer {token}'.format(token=ntfy_token)

    logging.debug('NTFY: Sending message to %s', ntfy_url)
    try:
        requests.post(ntfy_url, data=ntfy_message.encode(encoding='utf-8'), headers=ntfy_headers)
    except:
        logging.error('NTFY: Can not send message!')

def this_is_the_end():
    if mqttc.is_connected():
        logging.info('MQTT disconnecting')
        mqttc.loop_stop()
        mqttc.disconnect()

    logging.info('Closing Tesla API')
    tesla.close()

    logging.info('Exiting, bye...')
    exit(0)

def handle_sigterm(signum, frame):
    logging.info('Program interrupted by sigterm')
    this_is_the_end()

def main():
    vehicles = get_vehicles()

    if mqtt_enabled == True and mqtt_server != '':
        if mqtt_user != '' and mqtt_pass != '':
            logging.debug('MQTT setting user & pass')
            mqttc.username_pw_set(mqtt_user, mqtt_pass)

        mqttc.connect(mqtt_server, mqtt_port, 60)

        mqttc.loop_start()

    try:
        while True:
            current_time = time.time()

            for vehicle in vehicles:
                if 'skip' in vehicle and current_time < vehicle['skip']:
                    logging.debug('%s: Vehicle Offline or Senty OFF - Skipping (%i seconds)', vehicle['vin'], vehicle['skip'] - current_time)
                    continue

                vehicle['vehicle_online'] = False
                vehicle['sentry_enabled'] = False
                vehicle['sentry_triggered'] = False

                try:
                    logging.debug('%s: Getting status...', vehicle['vin'])
                    vehicle_state = vehicle.get_vehicle_data()['vehicle_state']
                except requests.exceptions.HTTPError as err:
                    if err.response.status_code == 408:
                        logging.info('%s: Vehicle is Offline or Sleeping', vehicle['vin'])
                    else:
                        logging.error('HTTP %i %s', err.response.status_code, err.response.text)
                    if mqtt_enabled == True:
                        update_mqtt(vehicle)
                    continue

                vehicle['vehicle_online'] = True

                if is_sentry_enabled(vehicle_state):
                    vehicle['sentry_enabled'] = True
                else:
                    logging.info('%s: Sentry Mode OFF', vehicle['vin'])
                    if timer_skip > timer:
                        logging.info('%s: Skipping this vehicle for %i seconds', vehicle['vin'], timer_skip)
                        vehicle['skip'] = current_time + timer_skip
                    if mqtt_enabled == True:
                        update_mqtt(vehicle)
                    continue

                if is_sentry_triggered(vehicle_state):
                    logging.info('%s: Sentry Mode ON - Triggered', vehicle['vin'])
                    vehicle['sentry_triggered'] = True
                else:
                    logging.info('%s: Sentry Mode ON - No Activity', vehicle['vin'])
                    vehicle['commands_sent'] = False
                    vehicle['ntfy_message_sent'] = False
                    if mqtt_enabled == True:
                        update_mqtt(vehicle)
                    continue

                if mqtt_enabled == True:
                    update_mqtt(vehicle)

                if not 'ntfy_message_sent' in vehicle:
                    vehicle['ntfy_message_sent'] = False

                if ntfy_enabled == True:
                    if vehicle['ntfy_message_sent'] == False:
                        ntfy_send_message(vehicle)
                        vehicle['ntfy_message_sent'] = True

            time.sleep(timer)

    except KeyboardInterrupt:
        logging.info('Interrupted by user input')
        this_is_the_end()

if __name__ == "__main__":
    logging.info('Starting with user account: %s', tesla_user)

    if mqtt_enabled == True:
        logging.info('MQTT Enabled %s:%s', mqtt_server, mqtt_port)

    if ntfy_enabled == True:
        logging.info('NTFY Enabled %s/%s', ntfy_server, ntfy_topic)

    signal.signal(signal.SIGTERM, handle_sigterm)
    main()
