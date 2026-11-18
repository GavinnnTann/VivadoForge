`timescale 1ns / 1ps
// spi_master - SPI mode 0 master (CPOL = 0, CPHA = 0), MSB first, one WIDTH-bit transfer per start.
//
//   spi_master #(.WIDTH(8), .CLK_DIV(4)) u_spi (
//       .clk(clk), .rst(1'b0), .start(go), .tx_data(cmd), .rx_data(reply), .busy(), .done(spi_done),
//       .sclk(sclk), .mosi(mosi), .miso(miso), .cs_n(cs_n));
//
// SCLK frequency = CLK_HZ / (2 * CLK_DIV). MOSI changes on the falling edge of SCLK and MISO is
// sampled on the rising edge. cs_n is low for the whole transfer; done pulses when rx_data is valid.
// miso comes from outside the FPGA: at slow SCLK rates (CLK_DIV >= 2) the sampling point is far
// from MISO's transitions, so no extra synchroniser is needed.
module spi_master #(
    parameter integer WIDTH   = 8,
    parameter integer CLK_DIV = 4
) (
    input  wire             clk,
    input  wire             rst,      // synchronous, active-high
    input  wire             start,
    input  wire [WIDTH-1:0] tx_data,
    output reg  [WIDTH-1:0] rx_data,
    output wire             busy,
    output reg              done,
    output reg              sclk,
    output reg              mosi,
    input  wire             miso,
    output reg              cs_n
);
    localparam integer DW = (CLK_DIV > 1) ? $clog2(CLK_DIV) : 1;
    localparam integer BW = $clog2(WIDTH + 1);

    reg [WIDTH-1:0] sh_tx  = {WIDTH{1'b0}};
    reg [WIDTH-1:0] sh_rx  = {WIDTH{1'b0}};
    reg [BW-1:0]    nbits  = {BW{1'b0}};
    reg [DW-1:0]    div    = {DW{1'b0}};
    reg             active = 1'b0;

    assign busy = active;

    initial begin
        rx_data = {WIDTH{1'b0}};
        done    = 1'b0;
        sclk    = 1'b0;
        mosi    = 1'b0;
        cs_n    = 1'b1;
    end

    always @(posedge clk) begin
        done <= 1'b0;
        if (rst) begin
            active <= 1'b0;
            cs_n   <= 1'b1;
            sclk   <= 1'b0;
            mosi   <= 1'b0;
        end else if (!active) begin
            sclk <= 1'b0;
            if (start) begin
                active <= 1'b1;
                cs_n   <= 1'b0;
                sh_tx  <= tx_data;
                mosi   <= tx_data[WIDTH-1];
                nbits  <= {BW{1'b0}};
                div    <= {DW{1'b0}};
            end
        end else if (div == CLK_DIV - 1) begin
            div <= {DW{1'b0}};
            if (!sclk) begin                          // rising edge: sample MISO
                sclk  <= 1'b1;
                sh_rx <= {sh_rx[WIDTH-2:0], miso};
            end else begin                            // falling edge: next bit or finish
                sclk  <= 1'b0;
                nbits <= nbits + 1'b1;
                if (nbits == WIDTH - 1) begin
                    active  <= 1'b0;
                    cs_n    <= 1'b1;
                    done    <= 1'b1;
                    rx_data <= sh_rx;
                end else begin
                    sh_tx <= {sh_tx[WIDTH-2:0], 1'b0};
                    mosi  <= sh_tx[WIDTH-2];
                end
            end
        end else begin
            div <= div + 1'b1;
        end
    end
endmodule
