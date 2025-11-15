import requests as re

url = "https://jsonplaceholder.typicode.com/users"

payload={}
headers={}
response=re.request("GET",url,headers=headers,data=payload)
print(response.text)