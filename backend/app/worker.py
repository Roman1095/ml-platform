import time


def main() -> None:
    print("ML Training Worker started")

    while True:
        print("Worker is waiting for training jobs...")
        time.sleep(10)


if __name__ == "__main__":
    main()