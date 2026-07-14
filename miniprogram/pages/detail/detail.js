const app = getApp();
const { drawQrCode } = require("../../utils/qrcode");

function formatDateTime(value) {
  return (value || "").replace("T", " ");
}

Page({
  data: { applicationNo: "", item: null, t: {} },
  onLoad(query) {
    this.applyLocale();
    this.setData({ applicationNo: query.applicationNo });
    this.load();
  },
  onShow() {
    this.applyLocale();
  },
  applyLocale() {
    this.setData({ t: app.t() });
    app.applyLanguage();
    wx.setNavigationBarTitle({ title: app.t().detailTitle });
  },
  async load() {
    const data = await app.request(`/api/appointments/${this.data.applicationNo}`);
    const item = data.item;
    item.visitAreasText = (item.visitAreas || []).join("、") || "-";
    item.visitStartDateTime = `${item.visitStartDate} 00:00:00`;
    item.visitEndDateTime = `${item.visitEndDate} 23:59:59`;
    item.companionText = item.visitors.length > 1 ? `${item.visitors.length - 1}${this.data.t.personUnit}` : "";
    item.approvalRecords = (item.approvalRecords || []).map((record) => ({
      ...record,
      actionTimeText: formatDateTime(record.actionTime)
    }));
    item.visitors = item.visitors.map((visitor, index) => ({
      ...visitor,
      visitorRole: index === 0 ? this.data.t.mainVisitor : this.data.t.companionVisitor,
      qrCanvasId: `visitor-qr-${index}`,
      visitStartDateTime: item.visitStartDateTime,
      visitEndDateTime: item.visitEndDateTime,
      visitPurpose: item.visitPurpose,
      applicantEmail: item.applicantEmail || "",
      specialRequest: item.specialRequest || "",
      carPlate: item.carPlate || visitor.carPlate || "",
      companionText: item.companionText,
      createdAt: formatDateTime(item.createdAt)
    }));
    this.setData({ item }, () => this.drawQrCodes());
  },
  drawQrCodes() {
    const visitors = (this.data.item && this.data.item.visitors) || [];
    visitors.forEach((visitor) => {
      if (visitor.qrPayload) {
        drawQrCode(this, visitor.qrCanvasId, visitor.qrPayload);
      }
    });
  },
  async getQr(event) {
    try {
      await app.request(`/api/appointments/${this.data.applicationNo}/visitors/${event.currentTarget.dataset.visitorId}/qr`);
      await this.load();
    } catch (error) {
      wx.showToast({ title: error.message, icon: "none" });
    }
  }
});
