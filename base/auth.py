"""Read-only authentication checks; no replays of business writes."""
import requests


class AuthenticationExpired(RuntimeError):
    pass


class PlatformUnavailable(RuntimeError):
    pass


def authenticated_get(client, endpoint, params=None):
    try:
        response = client.session.get(client.default_base_url + endpoint, params=params,
                                      timeout=(10, 30), allow_redirects=False)
    except requests.RequestException:
        raise PlatformUnavailable("暂时无法连接平台，登录缓存已保留，请稍后重试") from None
    if response.status_code == 401:
        raise AuthenticationExpired("平台登录已过期")
    if response.status_code != 200:
        raise PlatformUnavailable(f"平台返回 HTTP {response.status_code}，登录缓存已保留")
    try:
        data = response.json()
    except ValueError:
        raise PlatformUnavailable("平台响应无法解析，登录缓存已保留") from None
    if not isinstance(data, dict):
        raise PlatformUnavailable("平台返回了未知格式，登录缓存已保留")
    code = data.get("code", 200)
    if str(code) == "401":
        raise AuthenticationExpired("平台登录已过期")
    if str(code) != "200":
        raise PlatformUnavailable("平台未确认请求成功，登录缓存已保留")
    return data.get("data", data)
