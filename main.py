import os
import signal
import time
from datetime import datetime
import pytz
import logging
import teslapy
import requests
import paho.mqtt.client as mqtt

log_format = os.environ.get("LOG_FORMAT", "%(asctime)s %(levelname)s: %(message)s")
log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
timezone_str = os.environ.get('TZ', 'UTC')

tesla_user = os.environ.get("TESLA_USER")
cars_vin_filter = os.environ.get("CARS_VIN", "").upper()

timer = os.environ.get("TIMER", 10)

mqtt_enabled = os.environ.get("MQTT_ENABLED", "false")
mqtt_server = os.environ.get("MQTT_SERVER", "")
mqtt_port = os.environ.get("MQTT_PORT", 1883)
mqtt_user = os.environ.get("MQTT_USER", "")
mqtt_pass = os.environ.get("MQTT_PASS", "")
mqtt_topic_prefix = os.environ.get("MQTT_TOPIC", "tesla-sentry")

ntfy_enabled = os.environ.get("NTFY_ENABLED", "false")
ntfy_server = os.environ.get("NTFY_SERVER", "https://ntfy.sh")
ntfy_topic = os.environ.get("NTFY_TOPIC", "")
ntfy_token = os.environ.get("NTFY_TOKEN", "")

logging.basicConfig(format=log_format)
logging.getLogger().setLevel(level=log_level)

tesla = teslapy.Tesla(email=tesla_user, cache_file='/cache/cache.json')
mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

def current_time():
    timezone = pytz.timezone(timezone_str)
    current_time = datetime.now(timezone)
    return str(current_time)

def get_vehicles():
    logging.debug("Getting vehicle list")
    vehicles = tesla.vehicle_list()

    logging.info("Get %s vehicles from Tesla API", len(vehicles))

    if cars_vin_filter:
        vehicles = [vehicle for vehicle in vehicles if 'vin' in vehicle and vehicle['vin'] in cars_vin_filter]
        logging.info("Returning %s vehicles after VIN filter applied", len(vehicles))

    for vehicle in vehicles:
        logging.debug("%s - %s", vehicle["vin"], vehicle["display_name"])

    return vehicles

def is_sentry_active(vehicle):
    vehicle_state = []

    try:
        vehicle_state = vehicle.get_vehicle_data()["vehicle_state"]
    except requests.exceptions.HTTPError as err:
        if err.response.status_code == 408:
            logging.info('%s: vehicle is offline or asleep', vehicle['vin'])
        else:
            logging.error('HTTP %i %s', err.response.status_code, err.response.text)
        return False


    if "sentry_mode" not in vehicle_state or vehicle_state['sentry_mode'] == False:
        logging.info('%s: sentry mode is off', vehicle['vin'])
        return False

    if "center_display_state" in vehicle_state and vehicle_state['center_display_state'] == 7:
        logging.info('%s: sentry mode on - active', vehicle['vin'])
        return True
    else:
        logging.info('%s: sentry mode on - no activity', vehicle['vin'])

    return False

def update_mqtt(vehicle, active):
    mqtt_topic = "{prefix}/{vin}/".format(prefix=mqtt_topic_prefix, vin=vehicle["vin"])
    logging.debug("MQTT: Updating topic %s", mqtt_topic)

    mqttc.publish(mqtt_topic + "sentry_active", active)
    mqttc.publish(mqtt_topic + "last_update", current_time())


def ntfy_send_message(vehicle):
    if not ntfy_server or not ntfy_topic:
        logging.error("NTFY: Server or Topic not set!")
        return False

    ntfy_url = "{server}/{topic}".format(server=ntfy_server, topic=ntfy_topic)

    ntfy_message = "{name} triggered Sentry Mode alert!".format(name=vehicle["display_name"])
    ntfy_headers = {
        "Title": "Sentry Mode",
        "Priority": "high",
        "Tags": "warning"
    }

    if ntfy_token:
        logging.debug("NTFY: Sending message with auth token")
        ntfy_headers["Authorization"] = "Bearer {token}".format(token=ntfy_token)

    logging.debug("NTFY: Sending message to %s", ntfy_url)
    try:
        requests.post(ntfy_url, data=ntfy_message.encode(encoding='utf-8'), headers=ntfy_headers)
    except:
        logging.error("NTFY: Can not send message!")

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
    logging.info("Program interrupted by sigterm")
    this_is_the_end()

def main():
    vehicles = get_vehicles()
    ntfy_message_sent = False

    if mqtt_server and mqtt_enabled == "true":
        if mqtt_user and mqtt_pass:
            logging.debug('MQTT setting user & pass')
            mqttc.username_pw_set(mqtt_user, mqtt_pass)

        mqttc.connect(mqtt_server, mqtt_port, 60)

        mqttc.loop_start()

    try:
        while True:
            for vehicle in vehicles:
                logging.debug("%s: Getting status...", vehicle["vin"])
                
                sentry_active = is_sentry_active(vehicle)

                if mqtt_enabled and mqttc.is_connected():
                    update_mqtt(vehicle, sentry_active)
                
                if ntfy_enabled:
                    if ntfy_message_sent == False and sentry_active:
                        ntfy_send_message(vehicle, sentry_active)
                    ntfy_message_sent = sentry_active

            time.sleep(int(timer))

    except KeyboardInterrupt:
        logging.info("Interrupted by user input")
        this_is_the_end()

if __name__ == "__main__":
    logging.info("Starting with user account: %s", tesla_user)

    if mqtt_enabled:
        logging.info('MQTT Enabled %s:%s', mqtt_server, mqtt_port)

    if ntfy_enabled:
        logging.info("NTFY Enabled %s/%s", ntfy_server, ntfy_topic)

    signal.signal(signal.SIGTERM, handle_sigterm)
    main()
