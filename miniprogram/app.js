const { languageOptions, getLanguage, getDictionary } = require("./utils/i18n");

App({
  globalData: {
    apiBase: "http://127.0.0.1:18088",
    lastApplicationNo: "",
    language: getLanguage(),
    userProfile: null,
    loginCode: ""
  },
  onLaunch() {
    this.globalData.userProfile = wx.getStorageSync("vmsUserProfile") || null;
    this.applyLanguage();
  },
  t() {
    return getDictionary(this.globalData.language);
  },
  languageOptions() {
    return languageOptions;
  },
  setLanguage(language) {
    this.globalData.language = language;
    wx.setStorageSync("vmsLanguage", language);
    this.applyLanguage();
  },
  applyLanguage() {
    const t = this.t();
    wx.setNavigationBarTitle({ title: t.navTitle });
    wx.setTabBarItem({ index: 0, text: t.navHome });
    wx.setTabBarItem({ index: 1, text: t.navRecords });
    wx.setTabBarItem({ index: 2, text: t.navProfile });
  },
  wechatLogin() {
    wx.login({
      success: (res) => {
        this.globalData.loginCode = res.code || "";
      }
    });
  },
  saveUserProfile(profile = {}) {
    const current = this.globalData.userProfile || {};
    const next = { ...current, ...profile };
    this.globalData.userProfile = next;
    wx.setStorageSync("vmsUserProfile", next);
    return next;
  },
  request(path, options = {}) {
    const app = this;
    return new Promise((resolve, reject) => {
      wx.request({
        url: app.globalData.apiBase + path,
        method: options.method || "GET",
        data: options.data || {},
        header: { "Content-Type": "application/json" },
        success(res) {
          if (res.statusCode >= 200 && res.statusCode < 300) {
            resolve(res.data);
          } else {
            const details = res.data && Array.isArray(res.data.details) ? `：${res.data.details.join("；")}` : "";
            reject(new Error(((res.data && res.data.message) || app.t().requestFailed) + details));
          }
        },
        fail(error) {
          reject(new Error(error.errMsg || app.t().networkFailed));
        }
      });
    });
  }
});
