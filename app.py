from flask import Flask, render_template, request, jsonify
import requests
import json
import time
app = Flask(__name__)
apikey = "cae89675"
from unittest.mock import patch, Mock


container1 = {

}
container2 = {

}

def searchfilms(search_text, page=1):
    start_time = time.time()
    url = f"https://www.omdbapi.com/?s={search_text}&page={page}&apikey={apikey}" 
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        container1[search_text] = data
        print(f"Time for searchfilms API call: {time.time() - start_time} seconds")
        return data
    else:
        print("Failed to retrieve search results.")
        return None

    
def getmoviedetails(movie):
    url = "https://www.omdbapi.com/?i=" + movie["imdbID"] + "&apikey=" + apikey
    response = requests.get(url)
    if response.status_code == 200:
        data =  response.json()
        container2[movie["imdbID"]] =data
        return response.json()
    else:
        print("Failed to retrieve search results.")
        return None

def get_country_flag(fullname):

    url = f"https://restcountries.com/v3.1/name/{fullname}?fullText=true"
    response = requests.get(url)
    if response.status_code == 200:
        country_data = response.json()
        if country_data:
            return country_data[0].get("flags", {}).get("svg", None)
    print(f"Failed to retrieve flag for country code: {fullname}")
    return None

def merge_data_with_flags(filter, page=1):
    filmssearch = searchfilms(filter, page)
 
    moviesdetailswithflags = []
    for movie in filmssearch["Search"]:
         moviedetails = getmoviedetails(movie)
         countriesNames = moviedetails["Country"].split(",")
         countries = []
         for country in countriesNames:
            countrywithflag = {
                "name": country.strip(),
                "flag": get_country_flag(country.strip())
            }
            countries.append(countrywithflag)
         moviewithflags = {
            "title": moviedetails["Title"],
            "year": moviedetails["Year"],
            "countries": countries
         }
         moviesdetailswithflags.append(moviewithflags)

    return moviesdetailswithflags

@app.route("/")
def index():
    filter = request.args.get("filter", "").upper()
    return render_template("index.html", movies = merge_data_with_flags(filter))

@app.route("/api/movies")
def api_movies():
    filter = request.args.get("filter", "")
    page = int(request.args.get("page", 1))
    return jsonify(merge_data_with_flags(filter, page=page))



@patch("app.requests.get")
def test_searchfilms_caching(self, mock_requests_get):
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"Search": [{"Title": "Superman II", "imdbID": "tt0081573"}]}
    mock_requests_get.return_value = mock_response

    # First call, should call the actual API
    data = searchfilms("superman")
    self.assertIn("superman", container1)

    # Second call, should use the cached data
    data_cached = searchfilms("superman")
    mock_requests_get.assert_called_once()  # Ensures no additional API call


if __name__ == "__main__":
    app.run(debug=True)


