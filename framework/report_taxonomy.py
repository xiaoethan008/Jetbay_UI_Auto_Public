"""Shared business hierarchy and parameter parsing for every report format."""
import re
from pathlib import PurePosixPath


FRAMEWORK_FILES = {
    'test_api_chain_context': 'API 链路工具',
    'test_artifact_layout': '产物目录规范',
    'test_ci_environment_guard': '环境保护',
    'test_context_isolation': '浏览器隔离',
    'test_error_page_detection': '错误页识别工具',
    'test_exploration_journal': '探索证据记录',
    'test_locator_health': '定位器检查',
    'test_network_checker': '网络检查工具',
    'test_quality_gate': '质量门禁',
    'test_quality_report': '报告生成',
    'test_report_taxonomy': '报告模块分类',
    'test_regression_database_policy': '数据库访问策略',
    'test_trace_lifecycle': 'Trace 生命周期',
    'test_cleanup_product_test_leads': '测试数据清理',
}

# File names are implementation details; these names are the reporting contract.
BUSINESS_FILES = {
    **dict.fromkeys(('test_date_entry_regression', 'test_calendar_regression'), ('搜索与报价', '日期选择与校验')),
    **dict.fromkeys(('test_search_time_regression', 'test_polling_action_recovery'), ('搜索与报价', '日期轮询与恢复')),
    **dict.fromkeys(('test_submit_proposal', 'test_round_trip_submit_proposal', 'test_multi_city_submit_proposal'), ('搜索与报价', '方案提交')),
    'test_search_same_city_validation': ('搜索与报价', '搜索校验'),
    'test_search_price_contract': ('搜索与报价', '价格展示'),
    'test_thankyou_refresh': ('搜索与报价', '提交结果页'),
    **dict.fromkeys(('test_subscription_regression', 'test_subscription_results_regression', 'test_subscription_positive_regression', 'test_subscription_backend_regression'), ('空腿航班', '订阅与退订')),
    'test_empty_leg_page_regression': ('空腿航班', '列表与筛选'),
    'test_empty_leg_entry': ('空腿航班', '页面入口'),
    'test_empty_leg_search_regression': ('空腿航班', '搜索结果'),
    **dict.fromkeys(('test_empty_leg_recommendation_rules', 'test_empty_leg_recommendation_by_email'), ('空腿航班', '推荐逻辑')),
    'test_video_regression': ('视频中心', '视频内容与展示'),
    'test_account_regression': ('账号', '登录与会话'),
    'test_login': ('账号', '登录'),
    'test_profile_edit_regression': ('账号', '个人资料'),
    'test_membership_regression': ('会员权益', '会员页面'),
    'test_jet_card_entry': ('会员权益', 'Jet Card'),
    'test_travel_credit_entry': ('会员权益', 'Travel Credit'),
    'test_sos_ui_regression': ('SOS', '医疗信息与报价'),
    'test_sos_recommendation_api': ('SOS', '推荐逻辑'),
    'test_private_jet_entry': ('私人飞机包机', '包机入口'),
    'test_contact_us_modal': ('联系与咨询', '联系表单'),
    **dict.fromkeys(('test_affiliate_partner_requires_login', 'test_affiliate_partner_already_submitted'), ('合作伙伴', '合作申请')),
    'test_page_paths': ('站点基础', '路由与语言'),
    'test_404_seo': ('站点基础', '404 与 SEO'),
    'test_global_meta_regression': ('站点基础', 'SEO'),
    'test_home_banner': ('首页', 'Banner'),
    'test_home_empty_leg_display': ('首页', '空腿展示'),
    'test_home_popular_routes': ('首页', '热门航线'),
    'test_home_search_validation': ('搜索与报价', '首页搜索'),
    'test_home_specialty_flights': ('首页', '场景包机'),
    'test_home_logged_in_navigation': ('公共导航', '登录态导航'),
    'test_home_mobile_navigation': ('公共导航', '移动端导航'),
    'test_home_top_navigation': ('公共导航', '顶部导航'),
    'test_home_footer_links': ('公共导航', '页脚'),
    'test_company_menu_pages': ('公共导航', 'Company 菜单'),
    'test_services_menu_pages': ('公共导航', 'Services 菜单'),
    'test_plan_your_flight_menu_pages': ('公共导航', 'Plan Your Flight 菜单'),
    'test_membership_menu_pages': ('公共导航', '会员菜单'),
}


def extract_test_case_id(nodeid):
    """Only inspect pytest parameters, including browser-prefixed combinations."""
    name = nodeid.split('::', 1)[-1]
    if '[' not in name or not name.endswith(']'):
        return ''
    parameters = name.split('[', 1)[1][:-1]
    ids = set(re.findall(r'(?:^|-)\b(TC-\d{3})(?=-|$)', parameters))
    return next(iter(ids)) if len(ids) == 1 else ''


def classify_test(nodeid, source_module=''):
    stem = PurePosixPath(nodeid.replace('\\', '/').split('::', 1)[0]).stem
    if stem in FRAMEWORK_FILES:
        parent, child, scope = '自动化框架自检', FRAMEWORK_FILES[stem], 'framework'
    elif stem in BUSINESS_FILES:
        parent, child = BUSINESS_FILES[stem]
        scope = 'business'
        # Membership/SOS inventory rows already describe useful subfunctions.
        if parent in ('会员权益', 'SOS') and '/' in source_module:
            child = source_module.split('/', 1)[1].strip()
    else:
        scope = 'business'
        text = (source_module + ' ' + nodeid).lower()
        if 'sos' in text:
            parent, child = 'SOS', '日期与请求校验'
        elif 'fixed_price' in text or 'fixed price' in text or 'test_v413_departure_date_expired' in text:
            parent, child = '固定价格包机', '日期与报价'
        elif 'empty_leg' in text or 'empty leg' in text:
            parent, child = '空腿航班', '页面与推荐'
        elif 'policy' in text or 'cookie' in text:
            parent, child = '站点基础', '政策与 Cookie'
        elif 'v413' in text or '日期' in text:
            parent, child = '搜索与报价', '日期与线索校验'
        elif 'seo' in text:
            parent, child = '站点基础', 'SEO'
        else:
            parent, child = '待归类业务', source_module or stem.removeprefix('test_')
    return {'module': parent, 'submodule': child, 'module_path': parent + ' / ' + child, 'test_scope': scope}
