const app = getApp();

Page({
  data: { t: {} },
  onShow() {
    this.setData({ t: app.t() });
    app.applyLanguage();
    wx.setNavigationBarTitle({ title: app.t().navTitle });
  },
  goForm() {
    wx.navigateTo({ url: "/pages/form/form" });
  }
});
