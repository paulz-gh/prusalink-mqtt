from paho.mqtt.client import Client
from time import sleep, time
import requests
import pprint

from json import dumps

from config_handler import ConfigHandler


class PrinterHandler:
    def __init__(self):
        self.printer_ip = None
        self.api_key = None
        self.printer_status = None
        self.printer_info = None
        self.job_status = None
        self.thread_terminate = False

        # mqtt
        self.mqtt_client = None
        self.mqtt_connected = False
        self.last_dict = None

        self.config_handler = None

    def mqtt_on_connect(self, client, userdata, flags, rc):
        print(f'Connected with result code {rc}')
        self.mqtt_connected = True

    def mqtt_on_disconnect(self, client, userdata, rc):
        print(f'Disconnected with result code {rc}')
        self.mqtt_connected = False

    def connect(self, mqtt_client: Client, config_handler: ConfigHandler):
        print('Connecting to PrusaLink...')

        self.printer_ip = config_handler.get('prusalink', 'ip_address')
        self.api_key = config_handler.get('prusalink', 'api_key')

        self.mqtt_client = mqtt_client

        self.config_handler = config_handler

        self.mqtt_client.on_connect = self.mqtt_on_connect
        self.mqtt_client.on_disconnect = self.mqtt_on_disconnect

        # set will
        self.printer_info = self.get_printer_info()

        self.mqtt_client.connect(config_handler.get('mqtt_broker', 'broker_ip'),
                                 config_handler.get_int('mqtt_broker', 'broker_port'))

        return self

    def get_printer_status(self):
        api_url = f'http://{self.printer_ip}/api/v1/status'
        headers = {'X-Api-Key': self.api_key}

        response = requests.get(api_url, headers=headers)

        if response.status_code == 200:
            return response.json()
        else:
            print(f'Error getting printer status: {response.status_code} {response.reason}')

        return None

    def get_job_status(self):
        api_url = f'http://{self.printer_ip}/api/v1/job'
        headers = {'X-Api-Key': self.api_key}

        response = requests.get(api_url, headers=headers)

        if response.status_code == 200:
            return response.json()
        elif response.status_code != 204:
            print(f'Error getting job status: {response.status_code} {response.reason}')

        return None

    def get_print_progress_content(self, generate_last_wish=False):
        # {“Name”:string, “Description”:string, “elapsed_time_s”:int64, “progress_percent”:int}
        print_status = None

        if generate_last_wish:
            print_status = {
                'Printer': self.printer_info['hostname'],
                'Job': 'Not printing',
                'Elapsed_time_s': 0,
                'Progress_percent': 0
            }
        else:
            job_name = self.job_status['file']['name'] if self.job_status is not None else ""
            # if elapsed time is less than 1 second, replace job name with printer state
            if self.job_status is not None and "job" in self.printer_status is not None and "time_printing" in self.printer_status['job'] and self.printer_status['job']['time_printing'] < 1:
                job_name = self.printer_status['printer']['state']

            print_status = {
                'Printer': self.printer_info['hostname'],
                'Job': job_name,
                'Elapsed_time_s': self.printer_status['job']['time_printing'] if "job" in self.printer_status is not None and "time_printing" in self.printer_status['job'] else 0,
                'Progress_percent': self.printer_status['job']['progress'] if "job" in self.printer_status is not None else 0
            }

        return dumps(print_status)

    def get_printer_info(self):
        api_url = f'http://{self.printer_ip}/api/v1/info'
        headers = {'X-Api-Key': self.api_key}

        response = requests.get(api_url, headers=headers)

        if response.status_code == 200:
            return response.json()

        return None

    def publish_topics(self):
        topics = {
            'job_topic': dumps(self.job_status),
            'printer_topic': dumps(self.printer_status)
        }

        for topic in topics:
            if topics[topic] is not None:
                data = topics[topic]
                actual_topic = self.config_handler.get('mqtt_topics', topic)

                if self.last_dict is None or self.last_dict[topic] != data:
                    self.mqtt_client.publish(actual_topic, data, retain=True)
        self.last_dict = topics

    def loop_forever(self):
        print('PrusaLink loop_forever()')

        while not self.thread_terminate:
            self.printer_status = self.get_printer_status()
            self.job_status = self.get_job_status()
            self.printer_info = self.get_printer_info()

            if self.printer_status is not None and self.printer_info is not None:
                self.publish_topics()

            sleep(1)

    def stop(self):
        print('PrusaLink stop()')
        self.thread_terminate = True
