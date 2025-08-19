import json
from app.decompress_json import main

def handler(event, context):
    try:
        main()
    except Exception as e:
        print(e)
        return {
            "statusCode": 500,
            "body": json.dumps({"message": "Error"})
        }
    return {
        "statusCode": 200,
        "body": json.dumps({"message": "Success"})
    }