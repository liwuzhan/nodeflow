#!/usr/bin/env python3
"""
测试 web_server.py 中的 Web 服务功能
"""

import pytest
import json
import tempfile
import shutil
from pathlib import Path
from web_server import (
    app,
    socketio,
    get_parcels_list,
    load_parcel_data,
    save_parcel_data,
    delete_parcel_data,
    load_config,
    DATA_DIR,
)


@pytest.fixture
def client():
    """创建 Flask 测试客户端"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def temp_data_dir(monkeypatch, tmp_path):
    """创建临时数据目录"""
    temp_dir = tmp_path / "parcels"
    temp_dir.mkdir()
    monkeypatch.setattr('web_server.DATA_DIR', temp_dir)
    yield temp_dir
    # 清理临时目录
    if temp_dir.exists():
        shutil.rmtree(temp_dir)


class TestWebRoutes:
    """测试 HTTP 路由"""

    def test_index_route(self, client):
        """测试主页路由"""
        response = client.get('/')
        assert response.status_code == 200
        assert b'<!DOCTYPE html>' in response.data

    def test_get_parcels_empty(self, client, temp_data_dir):
        """测试获取空地块列表"""
        response = client.get('/api/parcels')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'parcels' in data
        assert data['parcels'] == []

    def test_create_parcel(self, client, temp_data_dir):
        """测试创建地块"""
        parcel_data = {
            'name': 'test_field',
            'description': '测试地块',
            'ref_point': {'lon': 121.5, 'lat': 31.2},
            'boundary_gps': [
                [121.5, 31.2],
                [121.501, 31.2],
                [121.501, 31.201],
            ],
            'vehicle': {
                'implement_width_m': 2.0,
                'overlap_ratio': 0.1,
                'path_inset_m': 0.5
            }
        }

        response = client.post(
            '/api/parcels',
            data=json.dumps(parcel_data),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True
        assert data['name'] == 'test_field'

    def test_get_parcel(self, client, temp_data_dir):
        """测试获取指定地块"""
        # 先创建一个地块
        parcel_data = {
            'name': 'test_field',
            'description': '测试地块',
            'ref_point': {'lon': 121.5, 'lat': 31.2},
            'boundary_gps': [[121.5, 31.2], [121.501, 31.2], [121.501, 31.201]],
            'boundary_enu': [[0, 0], [100, 0], [100, 100]],
        }
        save_parcel_data('test_field', parcel_data)

        # 获取地块
        response = client.get('/api/parcels/test_field')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['name'] == 'test_field'
        assert data['description'] == '测试地块'

    def test_get_parcel_not_found(self, client, temp_data_dir):
        """测试获取不存在的地块"""
        response = client.get('/api/parcels/nonexistent')
        assert response.status_code == 404

    def test_delete_parcel(self, client, temp_data_dir):
        """测试删除地块"""
        # 先创建一个地块
        parcel_data = {'name': 'test_field'}
        save_parcel_data('test_field', parcel_data)

        # 删除地块
        response = client.delete('/api/parcels/test_field')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

        # 验证已删除
        assert not (temp_data_dir / 'test_field.json').exists()


class TestParcelDataFunctions:
    """测试地块数据处理函数"""

    def test_save_and_load_parcel(self, temp_data_dir):
        """测试保存和加载地块"""
        parcel_data = {
            'name': 'test_field',
            'description': '测试地块',
            'ref_point': {'lon': 121.5, 'lat': 31.2},
            'boundary_gps': [[121.5, 31.2], [121.501, 31.2]],
        }

        # 保存
        success = save_parcel_data('test_field', parcel_data)
        assert success is True

        # 加载
        loaded_data = load_parcel_data('test_field')
        assert loaded_data is not None
        assert loaded_data['name'] == 'test_field'
        assert loaded_data['description'] == '测试地块'
        assert 'created_at' in loaded_data
        assert 'updated_at' in loaded_data

    def test_get_parcels_list(self, temp_data_dir):
        """测试获取地块列表"""
        # 创建多个地块
        for i in range(3):
            parcel_data = {
                'name': f'field_{i}',
                'description': f'测试地块 {i}',
            }
            save_parcel_data(f'field_{i}', parcel_data)

        # 获取列表
        parcels = get_parcels_list()
        assert len(parcels) == 3
        names = [p['name'] for p in parcels]
        assert 'field_0' in names
        assert 'field_1' in names
        assert 'field_2' in names

    def test_delete_parcel_data(self, temp_data_dir):
        """测试删除地块数据"""
        # 创建地块
        parcel_data = {'name': 'test_field'}
        save_parcel_data('test_field', parcel_data)

        # 删除
        success = delete_parcel_data('test_field')
        assert success is True

        # 验证已删除
        loaded = load_parcel_data('test_field')
        assert loaded is None

    def test_delete_nonexistent_parcel(self, temp_data_dir):
        """测试删除不存在的地块"""
        success = delete_parcel_data('nonexistent')
        assert success is False


class TestCoordinateConversionAPI:
    """测试坐标转换 API"""

    def test_gps_to_enu_conversion(self, client):
        """测试 GPS 到 ENU 转换 API"""
        data = {
            'mode': 'gps_to_enu',
            'lon': 121.501,
            'lat': 31.2,
            'ref_lon': 121.5,
            'ref_lat': 31.2
        }

        response = client.post(
            '/api/convert',
            data=json.dumps(data),
            content_type='application/json'
        )

        assert response.status_code == 200
        result = json.loads(response.data)
        assert 'x' in result
        assert 'y' in result
        assert result['x'] > 0  # 向东，X 应为正
        assert abs(result['y']) < 1  # 纬度相同，Y 应接近 0

    def test_enu_to_gps_conversion(self, client):
        """测试 ENU 到 GPS 转换 API"""
        data = {
            'mode': 'enu_to_gps',
            'x': 100,
            'y': 0,
            'ref_lon': 121.5,
            'ref_lat': 31.2
        }

        response = client.post(
            '/api/convert',
            data=json.dumps(data),
            content_type='application/json'
        )

        assert response.status_code == 200
        result = json.loads(response.data)
        assert 'lon' in result
        assert 'lat' in result
        assert result['lon'] > 121.5  # 向东，经度应增加
        assert abs(result['lat'] - 31.2) < 0.001  # 纬度应接近参考点


class TestParcelWithHoles:
    """测试带孔洞的地块"""

    def test_create_parcel_with_holes(self, client, temp_data_dir):
        """测试创建带孔洞的地块"""
        parcel_data = {
            'name': 'field_with_holes',
            'description': '带孔洞的地块',
            'ref_point': {'lon': 121.5, 'lat': 31.2},
            'boundary_gps': [
                [121.5, 31.2],
                [121.502, 31.2],
                [121.502, 31.202],
                [121.5, 31.202],
            ],
            'holes_gps': [
                # 孔洞 1
                [
                    [121.501, 31.201],
                    [121.5015, 31.201],
                    [121.5015, 31.2015],
                    [121.501, 31.2015],
                ]
            ],
            'vehicle': {
                'implement_width_m': 2.0,
                'overlap_ratio': 0.1,
                'path_inset_m': 0.5
            }
        }

        response = client.post(
            '/api/parcels',
            data=json.dumps(parcel_data),
            content_type='application/json'
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] is True

        # 验证保存的数据
        loaded = load_parcel_data('field_with_holes')
        assert loaded is not None
        assert 'holes_gps' in loaded
        assert len(loaded['holes_gps']) == 1
        assert len(loaded['holes_gps'][0]) == 4

        # 验证统计信息
        assert 'stats' in loaded
        assert loaded['stats']['holes'] == 1
        assert loaded['stats']['area'] > 0  # 面积应扣除孔洞


class TestConfiguration:
    """测试配置加载"""

    def test_load_config_defaults(self, monkeypatch, tmp_path):
        """测试默认配置"""
        # 使用不存在的配置文件路径
        fake_config = tmp_path / "nonexistent.json"
        monkeypatch.setattr('web_server.CONFIG_FILE', fake_config)

        config = load_config()
        assert 'amap_api_key' in config
        assert 'web_host' in config
        assert 'web_port' in config
        assert config['web_host'] == '0.0.0.0'
        assert config['web_port'] == 8081

    def test_load_config_from_file(self, monkeypatch, tmp_path):
        """测试从文件加载配置"""
        config_file = tmp_path / "config.json"
        config_data = {
            'amap_api_key': 'test_key',
            'amap_security_code': 'test_code',
            'web_port': 9999
        }
        config_file.write_text(json.dumps(config_data))

        monkeypatch.setattr('web_server.CONFIG_FILE', config_file)

        config = load_config()
        assert config['amap_api_key'] == 'test_key'
        assert config['amap_security_code'] == 'test_code'
        assert config['web_port'] == 9999

    def test_load_config_env_override(self, monkeypatch, tmp_path):
        """测试环境变量覆盖配置文件"""
        config_file = tmp_path / "config.json"
        config_data = {'amap_api_key': 'file_key'}
        config_file.write_text(json.dumps(config_data))

        monkeypatch.setattr('web_server.CONFIG_FILE', config_file)
        monkeypatch.setenv('AMAP_API_KEY', 'env_key')

        config = load_config()
        assert config['amap_api_key'] == 'env_key'  # 环境变量优先级更高


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
