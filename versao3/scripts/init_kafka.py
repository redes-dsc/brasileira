import time
import logging
import os
from kafka.admin import KafkaAdminClient, NewTopic
from kafka.errors import TopicAlreadyExistsError, NoBrokersAvailable

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")

TOPICS_CONFIG = [
    {"name": "fonte-assignments", "partitions": 3, "replication_factor": 1},
    {"name": "raw-articles", "partitions": 3, "replication_factor": 1},
    {"name": "classified-articles", "partitions": 3, "replication_factor": 1},
    {"name": "article-published", "partitions": 3, "replication_factor": 1},
    {"name": "pautas-especiais", "partitions": 1, "replication_factor": 1},
    {"name": "pautas-gap", "partitions": 1, "replication_factor": 1},
    {"name": "consolidacao", "partitions": 1, "replication_factor": 1},
    {"name": "homepage-updates", "partitions": 1, "replication_factor": 1},
    {"name": "breaking-candidate", "partitions": 1, "replication_factor": 1},
]

def wait_for_kafka() -> None:
    logger.info("Waiting for Kafka to be ready...")
    for _ in range(30):
        try:
            admin_client = KafkaAdminClient(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
            admin_client.close()
            logger.info("Kafka is ready.")
            return
        except NoBrokersAvailable:
            time.sleep(2)
    raise RuntimeError("Kafka did not become ready in time.")

def create_topics() -> None:
    admin_client = KafkaAdminClient(bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS)
    
    existing_topics = admin_client.list_topics()
    new_topics = []

    for cfg in TOPICS_CONFIG:
        if cfg["name"] not in existing_topics:
            new_topics.append(
                NewTopic(
                    name=cfg["name"], 
                    num_partitions=cfg["partitions"], 
                    replication_factor=cfg["replication_factor"]
                )
            )
    
    if new_topics:
        try:
            admin_client.create_topics(new_topics=new_topics)
            logger.info(f"Created topics: {[t.name for t in new_topics]}")
        except TopicAlreadyExistsError:
            logger.warning("Some topics already exist.")
        except Exception as e:
            logger.error(f"Failed to create topics: {e}")
    else:
        logger.info("All topics already exist.")

    admin_client.close()

if __name__ == "__main__":
    try:
        wait_for_kafka()
        create_topics()
    except Exception as e:
        logger.error(f"Initialization failed: {e}")
