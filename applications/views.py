from django import core
from django.http import JsonResponse, HttpResponse, QueryDict
from django.contrib import auth, messages
from django.contrib.auth.models import User, Group
from django.core.files.storage import default_storage
from django.forms.models import model_to_dict

from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, action
from django.db import connection

import json
import os
import re
import datetime
from operator import itemgetter
from math import sin, cos, sqrt, atan2, radians

from applications.crawler import get_weather_from_official
from applications.models import city, items, series, sights
from applications.serializers import *	
from constant import constant
import numpy
import pandas as pd

def trans_data_format(all_data : list, allow_columns : dict) -> list:
    result = []
    for element in all_data:
        _dict = {}
        for key, value in element.items():
            if key in allow_columns.keys():
                _dict[allow_columns.get(key)] = value
        result.append(_dict)
    return result

def getDistance(latA, lonA, latB, lonB):  
        R = 6373.0

        lat1 = radians(latA)
        lon1 = radians(lonA)
        lat2 = radians(latB)
        lon2 = radians(lonB)

        dlon = lon2 - lon1
        dlat = lat2 - lat1

        a = sin(dlat / 2)**2 + cos(lat1) * cos(lat2) * sin(dlon / 2)**2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        distance = R * c
        return distance

class Hello_World(APIView):
    def get(self, request):
        now_time = (datetime.datetime.now() + datetime.timedelta(hours=8)).strftime("%Y/%m/%d %H:%M:%S")
        text = f"""<h1> HELLOOOOOOOO WORLDDDDDDDDD!!!! 
        <br>我應該還在睡 不要亂攻擊我電腦 
        <br>YIOYOYOYOYOO!!!
        </h1>
        <br><h3> 現在時間是 : {now_time} </h3>
        """
        return HttpResponse(text)

class Travel_API(APIView):
    def get(self, request):
        request_data = request.data
        result = []
        for _element in request_data:
            travel_date_format = datetime.datetime.fromtimestamp(_element['time']/1000.0)
            travel_date = travel_date_format.strftime('%Y-%m-%d')

            sights_obj = sights.objects.get(id = _element['attraction_id'])
            series_obj = series.objects.filter(
                start_time__year = travel_date_format.date().year, 
                start_time__month = travel_date_format.date().month, 
                start_time__day = travel_date_format.date().day, 
                time_unit = _element['time_unit']
            )
            series_obj = series_obj.exclude(measure__in=['曝曬級數','自定義 Wx 單位', '公尺/秒'])
            description_list = {
                "MaxCI": {
                    "name" : "ciDescription",
                    "define" : constant.CI_LEVEL
                    },
                "UVI": {
                    "name" : "uviDescription",
                    "define" : constant.UVI_LEVEL
                    },
                "Wx": {
                    "name" : "wxDescription",
                    "define" : constant.WX_LEVEL
                    },
                "WS": {
                    "name" : "wsDescription",
                    "define" : constant.WS_LEVEL
                    },
            }

            dict_queryset_weather = {}
            for _obj in series_obj:
                _dict_content = _obj.__dict__
                _element_name = _obj.items.element_name    
                if _element_name in description_list.keys():
                    _new_description = description_list[_element_name]
                    dict_queryset_weather[_new_description['name']] = _new_description['define'][_dict_content['value']]
                dict_queryset_weather[_element_name] = _dict_content['value']
            dict_sights = sights_obj.__dict__
            del dict_sights['_state']
            result.append({
                'attraction' : dict_sights,
                'weather' : dict_queryset_weather,
            })

        return JsonResponse(result , safe=False)

    def post(self, request):
        request_data = request.data
        offset = request_data['offset']
        page_limit = request_data['limit']
        city_output_sql = u"""
            SELECT * FROM applications_city
            WHERE {filter_condition};
        """
        base_sql = u""" id IN (SELECT city_id
                FROM applications_series series
                INNER JOIN applications_items items ON (series.items_id = items.id)
                INNER JOIN applications_city city ON (series.city_id = city.id)
                WHERE {filter_condition})
            """

        dict_filter = []
        sub_filter_str = []
        include_data = ['Wx']
        measure_not_in = ['曝曬級數','自定義 Wx 單位']
        str_measure_not = "','".join(measure_not_in)
        travel_date_format = datetime.datetime.fromtimestamp(request_data['time']/1000.0)
        travel_date = travel_date_format.strftime('%Y-%m-%d')
        last_element_type = ""
        for element in request_data['rule']:
            if element['type'] in include_data:
                _str_value = ','.join([str(i) for i in element['value']])
                str_sql = f"(element_name = '{element['type']}' AND value IN ({_str_value}) AND DATE(start_time) = '{travel_date}' AND time_unit = '{request_data['time_unit']}')"
            else:
                str_sql = f"(element_name = '{element['type']}' AND value BETWEEN {element['lowValue']}  AND {element['highValue']} AND DATE(start_time) = '{travel_date}' AND time_unit = '{request_data['time_unit']}')"
  
            if last_element_type != element['type'] and last_element_type:
                sub_result = base_sql.format(
                    filter_condition = ' OR '.join(sub_filter_str)
                )
                dict_filter.append(sub_result)
                sub_filter_str = []
                
            sub_filter_str.append(str_sql)
            last_element_type = element['type']

        dict_filter.append(base_sql.format(
            filter_condition = ' OR '.join(sub_filter_str)
        ))

        result_sql = city_output_sql.format(
            filter_condition = ' AND '.join(dict_filter)
            )
        filter_as_data = pd.read_sql(result_sql.encode('utf8'), connection).to_dict('records')
        
        # mapping city and district
        postion_in_key = list(set([(i['city'], i['district']) for i in filter_as_data]))
        all_city_obj = city.objects.all()
        position_in_pk = []
        for val1, val2 in postion_in_key:
            position_in_pk.append(all_city_obj.get(city=val1, district= val2).pk)

        # weather
        weather_data = series.objects.filter(city_id__in = position_in_pk).exclude(measure__in=measure_not_in)

        dict_queryset_weather = {}
        weather_data = weather_data.filter(
            start_time__date = travel_date_format.date(),
            # start_time__year = travel_date_format.date().year, 
            # start_time__month = travel_date_format.date().month, 
            # start_time__day = travel_date_format.date().day, 
            time_unit = request_data['time_unit'],
            )
        
        weather_data = weather_data.prefetch_related('city')
        weather_data = weather_data.prefetch_related('items')
        description_list = {
            "MaxCI": {
                "name" : "ciDescription",
                "define" : constant.CI_LEVEL
                },
            "UVI": {
                "name" : "uviDescription",
                "define" : constant.UVI_LEVEL
                },
            "Wx": {
                "name" : "wxDescription",
                "define" : constant.WX_LEVEL
                },
            "WS": {
                "name" : "wsDescription",
                "define" : constant.WS_LEVEL
                },
        }

        for _obj in weather_data:
            city_key = f"{_obj.city.city},{_obj.city.district}"
            _dict_content = _obj.__dict__
            if not dict_queryset_weather.get(city_key, ''):
                dict_queryset_weather[city_key] = {}
            _element_name = _obj.items.element_name    
            if _element_name in description_list.keys():
                _new_description = description_list[_element_name]
                dict_queryset_weather[city_key][_new_description['name']] = _new_description['define'][_dict_content['value']]
            dict_queryset_weather[city_key][_element_name] = _dict_content['value']

        filtered_sights = []
        all_sights = sights.objects.all()
        for _data in filter_as_data:
            filtered_sights.extend(all_sights.filter(city=_data['city'], district= _data['district']).values())
        
        for element in filtered_sights:
            element['images'] = element['images'].split(',')
            element['url'] = element['url'].split(',')
            element['distance'] = getDistance(request_data['latitude'],request_data['longitude'],element['nlat'],element['elong'])

        filtered_sights = sorted(filtered_sights, key=itemgetter('distance'))

        # result
        result = []
        for i in filtered_sights:
            _dict_mapping = {}
            _dict_mapping['weather'] = dict_queryset_weather[f"{i['city']},{i['district']}"]
            _dict_mapping['attraction'] = i
            result.append(_dict_mapping)

        return JsonResponse(result[page_limit*(offset-1):page_limit*offset] , safe=False)

class Date_Processor(APIView):
    def get(self, request):
        return HttpResponse("")

    def post(self, request):
        # with open('./dist/weather.json', 'rb+') as f:
        #    all_data = json.load(f)
        request_data = request.data
        # import city
        for _data in get_weather_from_official(request_data['weather_token']):
            city_allow_columns = {
                'city' : 'city', 
                'location' : 'district', 
                'lat' : 'latitude', 
                'lon' : 'longitude'
            }
            with open('./result.txt','w+') as f:
                f.write(json.dumps(_data))
            city_data = trans_data_format(_data, city_allow_columns)
            city_data = [dict(t) for t in {tuple(d.items()) for d in city_data}]
            city_serializers = CitySerializers(data=city_data, context=request, many=True)
            if city_serializers.is_valid():
                city_serializers.save()
                # return Response(city_serializers.errors, status=status.HTTP_400_BAD_REQUEST)

            # import items
            items_allow_columns = {
                'description' : 'description', 
                'elementName' : 'element_name', 
            }
            items_data = trans_data_format(_data, items_allow_columns)
            items_data = [dict(t) for t in {tuple(d.items()) for d in items_data}]
            
            items_serializers = ItemsSerializers(data=items_data, context=request, many=True)
            if not items_serializers.is_valid():
                items_serializers.save()
                # return Response(items_serializers.errors, status=status.HTTP_400_BAD_REQUEST)
            
            # import series
            series_allow_columns = {
                'measures' : 'measure', 
                'value' : 'value', 
                'startTime' : 'start_time', 
                'endTime' : 'end_time',
                'time_unit' : 'time_unit',
                'location' : 'city',  #代替
                'elementName' : 'items',  #代替
            }
            series_data = trans_data_format(_data, series_allow_columns)
            items_obj = items.objects.all()
            city_obj = city.objects.filter(city=city_data[0]['city'])
            # print(items_obj.filter(element_name = 'PoP12h'), city_obj.filter(district='北投區'))
            items_mapping = {i['element_name']:i['id'] for i in items_obj.values('id','element_name') }
            city_mapping = {i['district']:i['id'] for i in city_obj.values('id','district') }

            for element in series_data:
                element['items'] = items_mapping[element['items']]
                element['city'] = city_mapping[element['city']]
            with open('./data.json', 'a+') as f:
                f.write(json.dumps(series_data))
            series_serializers = SeriesSerializers(data=series_data, context=request, many=True)
            if not series_serializers.is_valid():
                return Response(series_serializers.errors, status=status.HTTP_400_BAD_REQUEST)
            series_serializers.save()

        return JsonResponse({'message':'succeed'}, safe=False)

    def delete(self, request):
        return ""