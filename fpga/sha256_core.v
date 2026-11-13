// SHA-256 block compression core (FIPS 180-4), iterative:
// one round per clock, 64 rounds per block. Synthesizable
// Verilog-2001. The same RTL is the FPGA core and the ASIC core;
// only the synthesis flow differs.
//
// Interface: load state_in and a 512-bit block, pulse start;
// done rises with state_out = state_in compressed with block.

module sha256_core (
    input  wire         clk,
    input  wire         rst,
    input  wire         start,
    input  wire [511:0] block,
    input  wire [255:0] state_in,
    output reg          done,
    output reg  [255:0] state_out
);
    function [31:0] k_const;
        input [5:0] i;
        begin
            case (i)
                6'd0: k_const = 32'h428a2f98; 6'd1: k_const = 32'h71374491;
                6'd2: k_const = 32'hb5c0fbcf; 6'd3: k_const = 32'he9b5dba5;
                6'd4: k_const = 32'h3956c25b; 6'd5: k_const = 32'h59f111f1;
                6'd6: k_const = 32'h923f82a4; 6'd7: k_const = 32'hab1c5ed5;
                6'd8: k_const = 32'hd807aa98; 6'd9: k_const = 32'h12835b01;
                6'd10: k_const = 32'h243185be; 6'd11: k_const = 32'h550c7dc3;
                6'd12: k_const = 32'h72be5d74; 6'd13: k_const = 32'h80deb1fe;
                6'd14: k_const = 32'h9bdc06a7; 6'd15: k_const = 32'hc19bf174;
                6'd16: k_const = 32'he49b69c1; 6'd17: k_const = 32'hefbe4786;
                6'd18: k_const = 32'h0fc19dc6; 6'd19: k_const = 32'h240ca1cc;
                6'd20: k_const = 32'h2de92c6f; 6'd21: k_const = 32'h4a7484aa;
                6'd22: k_const = 32'h5cb0a9dc; 6'd23: k_const = 32'h76f988da;
                6'd24: k_const = 32'h983e5152; 6'd25: k_const = 32'ha831c66d;
                6'd26: k_const = 32'hb00327c8; 6'd27: k_const = 32'hbf597fc7;
                6'd28: k_const = 32'hc6e00bf3; 6'd29: k_const = 32'hd5a79147;
                6'd30: k_const = 32'h06ca6351; 6'd31: k_const = 32'h14292967;
                6'd32: k_const = 32'h27b70a85; 6'd33: k_const = 32'h2e1b2138;
                6'd34: k_const = 32'h4d2c6dfc; 6'd35: k_const = 32'h53380d13;
                6'd36: k_const = 32'h650a7354; 6'd37: k_const = 32'h766a0abb;
                6'd38: k_const = 32'h81c2c92e; 6'd39: k_const = 32'h92722c85;
                6'd40: k_const = 32'ha2bfe8a1; 6'd41: k_const = 32'ha81a664b;
                6'd42: k_const = 32'hc24b8b70; 6'd43: k_const = 32'hc76c51a3;
                6'd44: k_const = 32'hd192e819; 6'd45: k_const = 32'hd6990624;
                6'd46: k_const = 32'hf40e3585; 6'd47: k_const = 32'h106aa070;
                6'd48: k_const = 32'h19a4c116; 6'd49: k_const = 32'h1e376c08;
                6'd50: k_const = 32'h2748774c; 6'd51: k_const = 32'h34b0bcb5;
                6'd52: k_const = 32'h391c0cb3; 6'd53: k_const = 32'h4ed8aa4a;
                6'd54: k_const = 32'h5b9cca4f; 6'd55: k_const = 32'h682e6ff3;
                6'd56: k_const = 32'h748f82ee; 6'd57: k_const = 32'h78a5636f;
                6'd58: k_const = 32'h84c87814; 6'd59: k_const = 32'h8cc70208;
                6'd60: k_const = 32'h90befffa; 6'd61: k_const = 32'ha4506ceb;
                6'd62: k_const = 32'hbef9a3f7; 6'd63: k_const = 32'hc67178f2;
                default: k_const = 32'h00000000;
            endcase
        end
    endfunction

    function [31:0] rotr;
        input [31:0] x;
        input [4:0] n;
        begin rotr = (x >> n) | (x << (32 - n)); end
    endfunction

    reg [31:0] w [0:15];
    reg [31:0] a, b, c, d, e, f, g, h;
    reg [6:0] round;
    reg busy;

    wire [31:0] w_next =
        (rotr(w[14], 17) ^ rotr(w[14], 19) ^ (w[14] >> 10)) + w[9] +
        (rotr(w[1], 7) ^ rotr(w[1], 18) ^ (w[1] >> 3)) + w[0];

    wire [31:0] s1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25);
    wire [31:0] ch = (e & f) ^ (~e & g);
    wire [31:0] t1 = h + s1 + ch + k_const(round[5:0]) +
                     (round < 16 ? block[511 - round*32 -: 32] : w_next);
    wire [31:0] s0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22);
    wire [31:0] maj = (a & b) ^ (a & c) ^ (b & c);
    wire [31:0] t2 = s0 + maj;

    integer i;
    always @(posedge clk) begin
        if (rst) begin
            busy <= 0; done <= 0; round <= 0;
        end else if (start && !busy) begin
            busy <= 1; done <= 0; round <= 0;
            {a, b, c, d, e, f, g, h} <= state_in;
            for (i = 0; i < 16; i = i + 1)
                w[i] <= block[511 - i*32 -: 32];
        end else if (busy) begin
            h <= g; g <= f; f <= e; e <= d + t1;
            d <= c; c <= b; b <= a; a <= t1 + t2;
            if (round >= 16) begin
                for (i = 0; i < 15; i = i + 1)
                    w[i] <= w[i + 1];
                w[15] <= w_next;
            end
            if (round == 63) begin
                busy <= 0; done <= 1;
                state_out <= {
                    state_in[255:224] + (t1 + t2),
                    state_in[223:192] + a,
                    state_in[191:160] + b,
                    state_in[159:128] + c,
                    state_in[127:96]  + (d + t1),
                    state_in[95:64]   + e,
                    state_in[63:32]   + f,
                    state_in[31:0]    + g};
            end
            round <= round + 1;
        end else begin
            done <= 0;
        end
    end
endmodule
