#!/usr/bin/env python3
"""
GraphQL Schema to Postman Request Generator

This script fetches a GraphQL schema from an endpoint and generates
Postman-compatible request bodies for queries and mutations.
"""

import requests
import json
import argparse
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import sys


@dataclass
class GraphQLField:
    """Represents a GraphQL field with its type and arguments"""
    name: str
    type: str
    args: List[Dict[str, Any]]
    description: Optional[str] = None


@dataclass
class PostmanRequest:
    """Represents a Postman request structure"""
    name: str
    method: str
    url: str
    headers: Dict[str, str]
    body: Dict[str, Any]
    description: Optional[str] = None


class GraphQLSchemaParser:
    """Parses GraphQL schema and generates Postman requests"""
    
    def __init__(self, endpoint: str, headers: Optional[Dict[str, str]] = None):
        self.endpoint = endpoint
        self.headers = headers or {}
        self.schema = None
        self.types = {}
        
    def fetch_schema(self) -> Dict[str, Any]:
        """Fetch the GraphQL schema using introspection query"""
        introspection_query = """
        query IntrospectionQuery {
          __schema {
            queryType { name }
            mutationType { name }
            subscriptionType { name }
            types {
              ...FullType
            }
          }
        }
        
        fragment FullType on __Type {
          kind
          name
          description
          fields(includeDeprecated: true) {
            name
            description
            args {
              ...InputValue
            }
            type {
              ...TypeRef
            }
            isDeprecated
            deprecationReason
          }
          inputFields {
            ...InputValue
          }
          interfaces {
            ...TypeRef
          }
          enumValues(includeDeprecated: true) {
            name
            description
            isDeprecated
            deprecationReason
          }
          possibleTypes {
            ...TypeRef
          }
        }
        
        fragment InputValue on __InputValue {
          name
          description
          type { ...TypeRef }
          defaultValue
        }
        
        fragment TypeRef on __Type {
          kind
          name
          ofType {
            kind
            name
            ofType {
              kind
              name
              ofType {
                kind
                name
                ofType {
                  kind
                  name
                  ofType {
                    kind
                    name
                    ofType {
                      kind
                      name
                      ofType {
                        kind
                        name
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """
        
        payload = {
            "query": introspection_query
        }
        
        headers = {
            "Content-Type": "application/json",
            **self.headers
        }
        
        try:
            response = requests.post(self.endpoint, json=payload, headers=headers)
            response.raise_for_status()
            
            data = response.json()
            if 'errors' in data:
                raise Exception(f"GraphQL errors: {data['errors']}")
                
            self.schema = data['data']['__schema']
            self._build_types_map()
            return self.schema
            
        except requests.RequestException as e:
            raise Exception(f"Failed to fetch schema: {e}")
    
    def _build_types_map(self):
        """Build a map of type names to type definitions"""
        if not self.schema:
            return
            
        for type_def in self.schema.get('types', []):
            if type_def.get('name'):
                self.types[type_def['name']] = type_def
    
    def _get_type_string(self, type_ref: Dict[str, Any]) -> str:
        """Convert a GraphQL type reference to a string representation"""
        if not type_ref:
            return "Unknown"
            
        kind = type_ref.get('kind')
        name = type_ref.get('name')
        of_type = type_ref.get('ofType')
        
        if kind == 'NON_NULL':
            return f"{self._get_type_string(of_type)}!"
        elif kind == 'LIST':
            return f"[{self._get_type_string(of_type)}]"
        elif name:
            return name
        else:
            return "Unknown"
    
    def _generate_sample_value(self, type_ref: Dict[str, Any]) -> Any:
        """Generate a sample value for a given type"""
        type_str = self._get_type_string(type_ref)
        base_type = type_str.rstrip('!').strip('[]')
        
        # Handle basic scalar types
        if base_type in ['String', 'ID']:
            return "sample_string"
        elif base_type == 'Int':
            return 1
        elif base_type == 'Float':
            return 1.0
        elif base_type == 'Boolean':
            return True
        elif base_type in self.types:
            type_def = self.types[base_type]
            if type_def.get('kind') == 'ENUM':
                enum_values = type_def.get('enumValues', [])
                if enum_values:
                    return enum_values[0]['name']
            elif type_def.get('kind') == 'INPUT_OBJECT':
                # Generate sample input object
                sample_obj = {}
                for field in type_def.get('inputFields', []):
                    field_name = field['name']
                    field_type = field['type']
                    sample_obj[field_name] = self._generate_sample_value(field_type)
                return sample_obj
        
        return f"sample_{base_type.lower()}"
    
    def _build_query_string(self, field: GraphQLField, operation_type: str) -> str:
        """Build a GraphQL query string for a field"""
        args_str = ""
        if field.args:
            arg_parts = []
            for arg in field.args:
                arg_name = arg['name']
                arg_type = self._get_type_string(arg['type'])
                sample_value = self._generate_sample_value(arg['type'])
                
                # Format the argument value
                if isinstance(sample_value, str):
                    formatted_value = f'"{sample_value}"'
                elif isinstance(sample_value, dict):
                    formatted_value = json.dumps(sample_value).replace('"', '\\"')
                else:
                    formatted_value = str(sample_value).lower() if isinstance(sample_value, bool) else str(sample_value)
                
                arg_parts.append(f"{arg_name}: {formatted_value}")
            
            args_str = f"({', '.join(arg_parts)})"
        
        # Simple field selection - you might want to make this more sophisticated
        field_selection = "{\n    # Add your field selections here\n    id\n  }"
        
        return f"{operation_type} {{\n  {field.name}{args_str} {field_selection}\n}}"
    
    def generate_postman_requests(self) -> List[PostmanRequest]:
        """Generate Postman requests for all queries and mutations"""
        if not self.schema:
            raise Exception("Schema not loaded. Call fetch_schema() first.")
        
        requests = []
        
        # Process queries
        query_type_name = self.schema.get('queryType', {}).get('name')
        if query_type_name and query_type_name in self.types:
            query_type = self.types[query_type_name]
            for field in query_type.get('fields', []):
                field_obj = GraphQLField(
                    name=field['name'],
                    type=self._get_type_string(field['type']),
                    args=field.get('args', []),
                    description=field.get('description')
                )
                
                query_string = self._build_query_string(field_obj, 'query')
                
                request = PostmanRequest(
                    name=f"Query: {field['name']}",
                    method="POST",
                    url=self.endpoint,
                    headers={
                        "Content-Type": "application/json",
                        **self.headers
                    },
                    body={
                        "query": query_string,
                        "variables": {}
                    },
                    description=field.get('description')
                )
                requests.append(request)
        
        # Process mutations
        mutation_type_name = self.schema.get('mutationType', {}).get('name')
        if mutation_type_name and mutation_type_name in self.types:
            mutation_type = self.types[mutation_type_name]
            for field in mutation_type.get('fields', []):
                field_obj = GraphQLField(
                    name=field['name'],
                    type=self._get_type_string(field['type']),
                    args=field.get('args', []),
                    description=field.get('description')
                )
                
                mutation_string = self._build_query_string(field_obj, 'mutation')
                
                request = PostmanRequest(
                    name=f"Mutation: {field['name']}",
                    method="POST",
                    url=self.endpoint,
                    headers={
                        "Content-Type": "application/json",
                        **self.headers
                    },
                    body={
                        "query": mutation_string,
                        "variables": {}
                    },
                    description=field.get('description')
                )
                requests.append(request)
        
        return requests
    
    def export_postman_collection(self, requests: List[PostmanRequest], collection_name: str = "GraphQL API") -> Dict[str, Any]:
        """Export requests as a Postman collection"""
        collection = {
            "info": {
                "name": collection_name,
                "description": f"Generated from GraphQL endpoint: {self.endpoint}",
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
            },
            "item": []
        }
        
        for request in requests:
            item = {
                "name": request.name,
                "request": {
                    "method": request.method,
                    "header": [
                        {
                            "key": key,
                            "value": value,
                            "type": "text"
                        }
                        for key, value in request.headers.items()
                    ],
                    "body": {
                        "mode": "raw",
                        "raw": json.dumps(request.body, indent=2),
                        "options": {
                            "raw": {
                                "language": "json"
                            }
                        }
                    },
                    "url": {
                        "raw": request.url,
                        "host": [request.url]
                    }
                }
            }
            
            if request.description:
                item["request"]["description"] = request.description
            
            collection["item"].append(item)
        
        return collection


def main():
    """Main function to run the script"""
    parser = argparse.ArgumentParser(description="Generate Postman requests from GraphQL schema")
    parser.add_argument("endpoint", help="GraphQL endpoint URL")
    parser.add_argument("-o", "--output", default="graphql_postman_collection.json", 
                       help="Output file for Postman collection (default: graphql_postman_collection.json)")
    parser.add_argument("-n", "--name", default="GraphQL API", 
                       help="Collection name (default: GraphQL API)")
    parser.add_argument("-H", "--header", action="append", 
                       help="Additional headers in format 'Key: Value'")
    
    args = parser.parse_args()
    
    # Parse headers
    headers = {}
    if args.header:
        for header in args.header:
            if ':' in header:
                key, value = header.split(':', 1)
                headers[key.strip()] = value.strip()
            else:
                print(f"Warning: Invalid header format '{header}', should be 'Key: Value'")
    
    try:
        # Create parser and fetch schema
        parser = GraphQLSchemaParser(args.endpoint, headers)
        print(f"Fetching schema from {args.endpoint}...")
        schema = parser.fetch_schema()
        
        # Generate requests
        print("Generating Postman requests...")
        requests = parser.generate_postman_requests()
        
        # Export collection
        collection = parser.export_postman_collection(requests, args.name)
        
        # Write to file
        with open(args.output, 'w') as f:
            json.dump(collection, f, indent=2)
        
        print(f"Successfully generated {len(requests)} requests")
        print(f"Postman collection saved to: {args.output}")
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
