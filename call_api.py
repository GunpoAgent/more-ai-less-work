import requests


url = "https://dapi.kakao.com/v2/local/search/address.json"
headers = {"Authorization": f'KakaoAK f4ca9d9fc9096a0f4f26a636e9d0ee29'}
params = {'query': address, 'analyze_type': 'similar','size' : 1 }

def  geocode_kakao(address) -> dict:
    #call kakao api
    try:
        response = requests.get(url, headers=headers, params={"query": address, 'analyze_type': 'similar',
              'size' : 1})
        response.raise_for_status()  # check HTTP  error
        
        data = response.json()
        
        # .get()으로 안전하게 documents 추출
        documents = data.get('documents')
        
        if not documents:  # None이거나 빈 리스트
            return {"success": False}
        
        result = documents[0]
        
        return {
            "latitude": float(result.get('y', 0)),
            "longitude": float(result.get('x', 0)),
            "success": True
        }
        
    except requests.RequestException as e:
        return {"success": False}
    except (ValueError, KeyError) as e:
        return {"success": False}




