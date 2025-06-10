from kuma import RestClient

try:
    client = RestClient(
        url="https://kuma.example.com",
        token="YOUR_BEARER_TOKEN",
        verify=False,
    )
except Exception as ex:
    a = 2
b = 2