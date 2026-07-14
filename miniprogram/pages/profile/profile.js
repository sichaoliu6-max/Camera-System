const app = getApp();

Page({
  data: {
    t: {},
    languageIndex: 0,
    currentLanguageLabel: "",
    languageOptions: [],
    userProfile: {}
  },
  onShow() {
    this.refresh();
  },
  refresh() {
    const language = app.globalData.language;
    const languageOptions = app.languageOptions();
    const languageIndex = languageOptions.findIndex((item) => item.code === language);
    this.setData({
      t: app.t(),
      languageOptions,
      languageIndex: languageIndex >= 0 ? languageIndex : 0,
      currentLanguageLabel: languageOptions[languageIndex >= 0 ? languageIndex : 0].label,
      userProfile: app.globalData.userProfile || {}
    });
    app.applyLanguage();
    wx.setNavigationBarTitle({ title: app.t().navProfile });
  },
  onLanguageChange(event) {
    const index = Number(event.detail.value);
    const option = this.data.languageOptions[index];
    if (!option) return;
    app.setLanguage(option.code);
    this.refresh();
  },
  authorizeProfile() {
    wx.getUserProfile({
      desc: "用于访客中心展示微信头像和昵称",
      success: (res) => {
        const userInfo = res.userInfo || {};
        app.saveUserProfile({
          nickName: userInfo.nickName,
          avatarUrl: userInfo.avatarUrl
        });
        this.refresh();
      }
    });
  },
  onChooseAvatar(event) {
    app.saveUserProfile({ avatarUrl: event.detail.avatarUrl });
    this.refresh();
  },
  onPhoneNumber(event) {
    const detail = event.detail || {};
    if (detail.errMsg && detail.errMsg.indexOf("ok") === -1) return;
    app.saveUserProfile({
      phoneNumber: detail.phoneNumber || detail.purePhoneNumber || this.data.t.phoneAuthorized,
      phoneCode: detail.code || ""
    });
    this.refresh();
  }
});
