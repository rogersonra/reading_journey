import urllib.request
import json
from config import HARDCOVER_TOKEN

ENDPOINT = "https://api.hardcover.app/v1/graphql"

def gql(query, variables=None):
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        ENDPOINT,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {HARDCOVER_TOKEN}",
            "User-Agent": "ReadingJourney/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

# What fields does books have? Filter to series-related ones
print("=== books type fields (series-related) ===")
result = gql('{ __type(name: "books") { fields { name type { name kind ofType { name } } } } }')
for f in (result.get("data", {}).get("__type") or {}).get("fields") or []:
    if "series" in f["name"].lower() or "title" in f["name"].lower() or "release" in f["name"].lower() or "date" in f["name"].lower():
        print(f"  {f['name']}: {f['type']}")

# Try querying Jack Carr with just title + release_date
print("\n=== Jack Carr books (title + release_date only) ===")
result2 = gql("""
{
  authors(where: { name: { _eq: "Jack Carr" } }) {
    id
    name
    contributions(limit: 50) {
      book {
        title
        release_date
        book_series {
          position
          series {
            name
          }
        }
      }
    }
  }
}
""")
print(json.dumps(result2, indent=2))
